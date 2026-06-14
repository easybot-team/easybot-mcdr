from mcdreforged.api.all import *
import websockets
from easybot_mcdr.api.player import get_data_map, init_player_api
from easybot_mcdr.config import get_config, load_config, save_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.ws_ext import ExtendedEasyBotWsClient as EasyBotWsClient
from easybot_mcdr.impl.get_server_info import get_online_mode
import easybot_mcdr.impl.cross_server_chat
from easybot_mcdr.impl.prefix_handler import PrefixNameHandler
from easybot_mcdr.impl.rcon_auto_config import check_and_configure_rcon
import re
import json
import os
import asyncio
import time
import traceback

# 全局变量
wsc: EasyBotWsClient = None
player_data_map = {}
rcon_initialized = False
exit_reported_at = {}
debounce_time = 5
kick_map = {}

from easybot_mcdr.meta import get_plugin_version
from easybot_mcdr.rpc import bind_registered_handlers
import easybot_mcdr.impl.rpc_handlers  # 注册 bridge_rpc 处理器

help_msg = '''--------§a EasyBot §r(版本: §e{0}§r)--------
§b!!ez help §f- §c显示帮助菜单
§b!!ez reload §f- §c重载配置文件

§c绑定类
§b!!ez bind §f- §c触发绑定
§b!!bind §f- §c同上

§c消息发送类
§b!!ez say <message> §f- §c发送消息
§b!!esay <message> §f- §c同上
§b!!say <message> §f- §c同上

§cRCON配置(需MCDR 3级权限及以上)
§b!!ez rcon auto §f- §c自动配置RCON
§b!!ez rcon status §f- §c查看RCON状态

§c假人过滤设置(需MCDR 3级权限及以上)
§b!!ez bot toggle §f- §c开启/关闭假人过滤
§b!!ez bot add <prefix> §f- §c添加假人过滤前缀
§b!!ez bot remove <prefix> §f- §c移除假人过滤前缀
§b!!ez bot list §f- §c显示假人过滤前缀列表

§c插件信息
§b!!ez §f- §c显示插件详情
---------------------------------------------'''.format(get_plugin_version())


def is_bot_player(player: str) -> bool:
    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    if not bot_filter.get("enabled", True):
        return False
    prefixes = bot_filter.get("prefixes", ["Bot_", "BOT_", "bot_"])
    return any(player.startswith(prefix) for prefix in prefixes)


def fix_mcdr_encoding(server: PluginServerInterface):
    """检查并修复 MCDR 的编码配置，确保能正确处理中文"""
    try:
        import os
        config_path = os.path.join(os.getcwd(), "config.yml")

        if not os.path.exists(config_path):
            server.logger.debug("未找到 MCDR config.yml，跳过编码检查")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查 decoding 配置
        # 期望格式: decoding: ['utf8', 'gbk']
        lines = content.split("\n")
        modified = False
        new_lines = []

        for line in lines:
            stripped = line.strip()
            # 匹配 decoding: utf8 或 decoding: "utf8" 等格式
            if stripped.startswith("decoding:") and "gbk" not in stripped:
                # 检查是否是单个值（不是列表）
                value = stripped.split(":", 1)[1].strip()
                if value.startswith("["):
                    # 已经是列表格式，但没有 gbk
                    if "gbk" not in value:
                        # 在列表中添加 gbk
                        value = value.rstrip("]").rstrip()
                        new_line = line.replace(stripped, f"decoding: {value}, 'gbk']")
                        new_lines.append(new_line)
                        modified = True
                        server.logger.info(f"已修复 MCDR decoding 配置: 添加 gbk 支持")
                        continue
                else:
                    # 单个值格式，改为列表
                    new_line = line.replace(stripped, f"decoding: ['utf8', 'gbk']")
                    new_lines.append(new_line)
                    modified = True
                    server.logger.info(f"已修复 MCDR decoding 配置: {value} -> ['utf8', 'gbk']")
                    continue
            new_lines.append(line)

        if modified:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
            server.logger.info("MCDR 编码配置已修复")
            # 设置标志，以便在命令注册后执行 reload
            server._easybot_encoding_fixed = True
        else:
            server.logger.debug("MCDR decoding 配置正常，无需修改")

    except Exception as e:
        server.logger.warning(f"检查 MCDR 编码配置时出错: {e}")


async def on_load(server: PluginServerInterface, prev_module):
    """插件加载时执行的函数"""
    global server_interface, wsc
    server_interface = server
    server.logger.info("开始加载EasyBot插件...")

    try:
        # 加载配置
        load_config(server)

        # 检查并修复 MCDR 的编码配置
        fix_mcdr_encoding(server)

        # 初始化 behavior_impl (PlayerDataGetter 等)
        from easybot_mcdr import behavior_impl
        behavior_impl.set_server(server)

        # 启动本地图片服务器（如果启用了图片上传）
        if get_config().get("image_upload", {}).get("enabled"):
            from easybot_mcdr.impl.chat_image import start_local_image_server
            start_local_image_server()

        # 注册服务器处理器
        config = get_config()
        if config.get("handler", {}).get("enabled", True):
            server.register_server_handler(PrefixNameHandler())
            server.logger.info("已启用自定义前缀处理器")
        else:
            server.logger.info("使用 MCDR 默认处理器")

        # 启动UUID检查线程
        start_uuid_check_thread(server)
        
        # 加载玩家数据
        load_player_data(server)
        
        # 初始化WebSocket客户端
        wsc = await initialize_websocket_client(server)
        # 绑定已注册的 RPC 处理器（装饰器可能在加载时已注册）
        bind_registered_handlers()
        
        # 注册事件监听器
        register_event_listeners(server)

        # 注册命令
        register_commands(server)

        # 如果编码配置被修改，提示用户手动执行
        if getattr(server, '_easybot_encoding_fixed', False):
            server.logger.info("编码配置已修改，请手动执行 !!MCDR reload config 使配置生效")

        # 检查 RCON 配置
        if not server.is_rcon_running():
            from easybot_mcdr.rcon_config import check_rcon_config
            status = check_rcon_config(server)
            if status["needs_config"]:
                server.logger.warning("§cRCON 未配置! 部分功能(命令执行、玩家皮肤获取)可能受限。")
                server.logger.warning("§e使用 §b!!ez rcon auto §e自动配置RCON")

        server.logger.info("EasyBot插件加载完成")
    except Exception as e:
        server.logger.error(f"插件加载过程中发生错误: {str(e)}")
        server.logger.debug("\n{traceback.format_exc()}")
        raise


def sync_online_players_with_rcon(server: PluginServerInterface, max_retries=5, retry_delay=2):
    """
    使用RCON同步在线玩家列表，带重试机制
    """
    for attempt in range(max_retries):
        try:
            if not server.is_rcon_running():
                server.logger.warning(f"RCON未运行 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    server.logger.error("RCON连接失败，无法同步玩家列表")
                    return False

            server.logger.info(f"正在通过RCON同步玩家列表 (尝试 {attempt + 1}/{max_retries})")
            result = server.rcon_query('list')
            
            # 检查 RCON 查询结果是否有效
            if result is None:
                server.logger.warning(f"RCON查询返回空结果 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    server.logger.error("RCON查询持续返回空结果，请检查RCON连接状态")
                    return False
            
            # 增强正则表达式兼容性
            match = re.search(
                r'There are (\d+) of a max (\d+) players online[^\d]*?(?:[:]?\s*(.*))?$',
                result,
                re.IGNORECASE
            )
            
            actual_online = []  # 初始化默认值
            if match:
                online_count = int(match.group(1))
                max_players = int(match.group(2))
                player_list_str = match.group(3) or ''  # 处理可能的 None
                actual_online = [p.strip() for p in player_list_str.split(',') if p.strip()]
                
                server.logger.info(f"RCON查询成功: {online_count}/{max_players} 玩家在线")
                if actual_online:
                    server.logger.info(f"在线玩家: {', '.join(actual_online)}")
            else:
                server.logger.warning(f"无法解析RCON列表输出，原始输出: {result}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    return False
            
            # 更新在线玩家列表
            player_data_map = get_data_map()
            if "online_players" in player_data_map:
                online_players = player_data_map["online_players"]
                removed_players = []
                for player in list(online_players.keys()):
                    if player not in actual_online:
                        online_players.pop(player)
                        removed_players.append(player)
                
                if removed_players:
                    server.logger.info(f"从在线玩家列表移除了: {', '.join(removed_players)}")
                else:
                    server.logger.info("在线玩家列表已同步，无需移除玩家")
            
            server.logger.info("RCON玩家列表同步完成")
            return True
            
        except Exception as e:
            server.logger.warning(f"RCON同步尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
            else:
                server.logger.error("RCON玩家列表同步最终失败")
                return False
    
    return False


from easybot_mcdr.impl.rcon_auto_config import check_and_configure_rcon

@new_thread("EasyBot Startup")
def on_server_started(server: PluginServerInterface):
    """服务器启动时执行的函数"""
    global wsc, rcon_initialized
    server.logger.info("检测到服务器启动事件，开始处理...")
    
    try:
        # 检查并配置RCON
        server.logger.info("开始RCON自动配置检查...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 执行RCON配置
            rcon_success = loop.run_until_complete(check_and_configure_rcon(server))
            
            # 如果RCON配置成功，设置标志
            if rcon_success:
                rcon_initialized = True
                server.logger.info("RCON初始化标志已设置")
            
            # 执行WebSocket连接和上报
            if wsc is not None:
                loop.run_until_complete(setup_websocket_and_report(server))
            else:
                server.logger.error("WebSocket客户端未初始化")

            if wsc:
        # 由于 on_server_started 是同步线程，需要用 run_coroutine_threadsafe
                asyncio.run_coroutine_threadsafe(
                    wsc.data_record("Online", "Server Started", "System"),
                    asyncio.get_event_loop()
                )
        finally:
            loop.close()
        
        # 进行RCON同步（如果可用）
        sync_online_players_if_available(server)
        
    except Exception as e:
        server.logger.error(f"启动过程中发生未预期错误: {type(e).__name__}: {str(e)}")
        server.logger.debug("\n{traceback.format_exc()}")

async def setup_websocket_and_report(server: PluginServerInterface):
    """设置WebSocket连接并上报服务器信息"""
    global wsc
    
    # 确保WebSocket连接已建立
    if not await ensure_websocket_connection(server):
        return False
    
    # 上报服务器信息
    try:
        await report_server_info(server)
        
        # 上报当前在线玩家
        await report_online_players(server)
        
        return True
    except Exception as e:
        server.logger.error(f"上报信息时出错: {str(e)}")
        server.logger.debug("\n{traceback.format_exc()}")
        return False

async def ensure_websocket_connection(server: PluginServerInterface):
    """确保WebSocket连接已建立"""
    global wsc
    if wsc is None:
        server.logger.error("WebSocket客户端未初始化")
        return False
    
    try:
        server.logger.info("检查WebSocket连接状态...")
        
        # 检查是否已连接（通过检查_ws属性和状态）
        if hasattr(wsc, '_ws') and wsc._ws is not None and hasattr(wsc._ws, 'state') and wsc._ws.state is websockets.State.OPEN:
            server.logger.info("WebSocket已连接")
            return True
        
        # 使用wsc内部的连接管理机制
        server.logger.info("WebSocket未连接，尝试启动连接...")
        await wsc.start()
        server.logger.info("WebSocket连接启动成功")
        return True
            
    except Exception as e:
        # 简单记录错误，详细的连接逻辑由wsc内部处理
        server.logger.warning(f"WebSocket初始化错误: {type(e).__name__}: {str(e)}")
        server.logger.error("WebSocket连接失败，请检查以下内容:")
        server.logger.error("- WebSocket服务端是否运行")
        server.logger.error("- 配置是否正确 (地址: %s)", get_config().get("ws", ""))
        server.logger.error("- 网络连接是否正常")
        return False

async def report_server_info(server: PluginServerInterface):
    """上报服务器信息"""
    global wsc
    server.logger.info("开始上报服务器信息...")
    
    server_info = {
        'name': server.get_server_information().name,
        'version': server.get_server_information().version,
        'player_count': len(server.get_online_players()),
        'max_players': server.get_server_information().max_players,
        'motd': server.get_server_information().description,
        'port': server.get_server_information().port
    }
    
    await wsc._send_packet("REPORT_SERVER_INFO", server_info)
    server.logger.info("服务器信息上报成功")

async def report_online_players(server: PluginServerInterface):
    """上报当前在线玩家"""
    global wsc
    
    for player in server.get_online_players():
        try:
            if not is_bot_player(player):
                await wsc.report_player(player)
                server.logger.debug(f"玩家 {player} 信息上报成功")
        except Exception as e:
            server.logger.error(f"上报玩家 {player} 信息失败: {str(e)}")
            server.logger.debug("\n{traceback.format_exc()}")

def sync_online_players_if_available(server: PluginServerInterface):
    """如果RCON可用，同步在线玩家列表"""
    import time
    
    # 等待一下确保服务器完全启动
    time.sleep(2)
    
    # 只有当RCON可用时才进行同步
    if server.is_rcon_running():
        server.logger.info("开始同步在线玩家列表...")
        sync_online_players_with_rcon(server)
    else:
        server.logger.warning("RCON未连接，跳过玩家列表同步")

async def show_help(source: CommandSource):
    for line in help_msg.splitlines():
        source.reply(line)

async def show_plugin_info(source: CommandSource):
    """显示插件详情信息"""
    from easybot_mcdr.meta import get_plugin_version
    from easybot_mcdr.impl.get_server_info import get_online_mode
    
    plugin_info = [
        '--------§a EasyBot 插件详情 §r--------',
        f'§b插件版本: §f{get_plugin_version()}',
        '§b插件名称: §fEasyBot MCDR',
        '§b功能介绍: §f跨服务器聊天、玩家数据同步、假人过滤',
        f'§b服务器模式: §f{'正版' if get_online_mode() else '离线'}模式',
        '§b使用帮助: §f!!ez help',
        '---------------------------------------------'
    ]
    
    for line in plugin_info:
        source.reply(line)

async def on_unload(server: PluginServerInterface):
    global player_data_map, wsc, server_interface

    try:
        # 停止本地图片服务器
        from easybot_mcdr.impl.chat_image import stop_local_image_server
        stop_local_image_server()
        # 在关闭连接前，上报服务器关闭（仅在已连接时尝试）
        if wsc:
            try:
                connected = False
                if hasattr(wsc, "is_connected"):
                    try:
                        connected = await wsc.is_connected()  # type: ignore
                    except Exception:
                        connected = False
                if connected:
                    await wsc.data_record("Offline", "Server Stopped", "System")
                else:
                    server.logger.info("WebSocket 未连接，跳过下线上报")
            except Exception as e:
                server.logger.warning(f"跳过下线上报，原因: {e}")
            
        # 保存玩家数据
        player_data_map = get_data_map()
        
        # 安全处理所有数据字段
        def safe_convert(data):
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return {k: v.__dict__ if hasattr(v, '__dict__') else v for k, v in data.items()}
            return {}
            
        data_to_save = {
            "online_players": safe_convert(player_data_map.get("online_players", [])),
            "uuid_map": safe_convert(player_data_map.get("uuid_map", {})),
            "cache": safe_convert(player_data_map.get("cache", []))
        }
        
        server.logger.debug(f"准备保存的数据: {data_to_save}")
        
        with open("easybot_cache.json", "w") as f:
            json.dump(data_to_save, f, indent=2)
        
        # 关闭连接和清理资源
        await close()
        
        # 清理全局变量
        player_data_map = {}
        server_interface = None
        
        server.logger.info("插件已完全卸载")
    except Exception as e:
        server.logger.error(f"卸载插件时出错: {e}")
        server.logger.debug("\n{traceback.format_exc()}")
        raise

async def close():
    global wsc
    if wsc is not None:
        try:
            await wsc.stop()
            # 确保连接完全关闭
            if hasattr(wsc, '_ws') and wsc._ws is not None:
                await wsc._ws.close()
            # 取消可能的心跳任务
            if hasattr(wsc, '_heartbeat_task') and wsc._heartbeat_task is not None:
                wsc._heartbeat_task.cancel()
                try:
                    await wsc._heartbeat_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            server_interface.logger.error(f"关闭连接时出错: {e}")
            server.logger.debug("\n{traceback.format_exc()}")
        finally:
            wsc = None

def start_uuid_check_thread(server: PluginServerInterface):
    """启动UUID同步检查线程"""
    import threading
    uuid_check_thread = threading.Thread(target=periodic_uuid_check, daemon=True)
    uuid_check_thread.start()
    server.logger.info("UUID同步检查线程已启动")

def load_player_data(server: PluginServerInterface):
    """加载玩家数据"""
    from easybot_mcdr.api.player import PlayerInfo
    
    if os.path.exists("easybot_cache.json"):
        server.logger.info("检测到缓存文件，加载玩家数据...")
        try:
            with open("easybot_cache.json", "r") as f:
                saved_data = json.load(f)
            
            # 处理online_players数据
            online_players = {}
            if isinstance(saved_data["online_players"], list):
                server.logger.warning("检测到旧版列表格式的online_players，正在转换...")
                for player_info in saved_data["online_players"]:
                    if isinstance(player_info, dict):
                        name = player_info.get("name")
                        if name:
                            online_players[name] = PlayerInfo(**player_info)
            elif isinstance(saved_data["online_players"], dict):
                online_players = {k: PlayerInfo(**v) for k, v in saved_data["online_players"].items()}
            else:
                server.logger.error(f"未知的online_players格式: {type(saved_data['online_players'])}")
                
            # 处理cache数据
            cache = {}
            if isinstance(saved_data["cache"], list):
                server.logger.warning("检测到旧版列表格式的cache，正在转换...")
                for player_info in saved_data["cache"]:
                    if isinstance(player_info, dict):
                        name = player_info.get("name")
                        if name:
                            cache[name] = PlayerInfo(**player_info)
            elif isinstance(saved_data["cache"], dict):
                cache = {k: PlayerInfo(**v) for k, v in saved_data["cache"].items()}
            else:
                server.logger.error(f"未知的cache格式: {type(saved_data['cache'])}")

            # 初始化玩家API
            init_player_api(server, {
                "online_players": online_players,
                "uuid_map": saved_data["uuid_map"],
                "cache": cache
            })
            
            # 删除旧缓存文件
            os.remove("easybot_cache.json")
        except Exception as e:
            server.logger.error(f"加载玩家数据时出错: {str(e)}")
            server.logger.debug("\n{traceback.format_exc()}")
            init_player_api(server, None)
    else:
        server.logger.info("未找到缓存文件，初始化空玩家数据")
        init_player_api(server, None)
    
    server.logger.info("玩家数据加载完成")

async def initialize_websocket_client(server: PluginServerInterface):
    """初始化WebSocket客户端"""
    global wsc
    server.logger.info("初始化WebSocket客户端...")
    
    # 关闭现有连接
    if wsc is not None:
        server.logger.info("关闭现有WebSocket连接...")
        try:
            await wsc.stop()
        except Exception as e:
            server.logger.error(f"关闭现有连接时出错: {str(e)}")
            server.logger.debug("\n{traceback.format_exc()}")
    
    # 直接使用EasyBotWsClient，不再创建增强版本
    # is_connected方法已在ws.py中实现
    
    # 创建客户端实例
    ws_url = get_config().get("ws", "")
    if not ws_url:
        server.logger.error("未找到WebSocket配置!")
        return None
    
    server.logger.info(f"WebSocket配置URL: {ws_url}")
    wsc = EasyBotWsClient(ws_url)
    
    # 直接启动连接，依赖ws.py中的指数退避重连机制
    try:
        await wsc.start()
        server.logger.info("WebSocket连接已启动")
    except Exception as e:
        # 简单记录错误，详细的重连和错误日志由ws.py内部处理
        server.logger.warning(f"WebSocket初始化错误: {type(e).__name__}")
    
    return wsc

# 移除不再使用的connect_websocket函数

def register_event_listeners(server: PluginServerInterface):
    """注册事件监听器"""
    from easybot_mcdr.impl.player_events import on_player_joined, on_player_left, on_player_death, on_info
    from easybot_mcdr.impl.chat_sync import on_user_info

    server.logger.info("注册事件监听器...")

    server.register_event_listener('server_started', on_server_started, priority=50)
    server.register_event_listener('mcdr.general_info', on_info, priority=1)
    server.register_event_listener('player_death', on_player_death)
    server.register_event_listener('mcdr.player_left', on_player_left)
    server.register_event_listener('player_left', on_player_left)
    # 注意: mcdr.player_joined 事件已在 player.py 的 init_player_api() 中以优先级1注册
    # 这里使用优先级10，确保在 player.py 的数据更新之后执行上报逻辑
    server.register_event_listener('mcdr.player_joined', on_player_joined, priority=10)
    server.register_event_listener('mcdr.user_info', on_user_info)

    server.logger.info("事件监听器注册完成")

def register_commands(server: PluginServerInterface):
    """注册命令"""
    builder = SimpleCommandBuilder()
    # 定义参数
    builder.arg("message", Text)  
    builder.arg("prefix", Text)   

    # 注册命令
    builder.command("!!ez help", show_help)
    builder.command("!!ez", show_plugin_info)
    builder.command("!!ez reload", reload)
    builder.command("!!ez bind", bind)
    builder.command("!!bind", bind)
    builder.command("!!say <message>", say)
    builder.command("!!esay <message>", say)
    builder.command("!!ez say <message>", say)

    # RCON 配置命令
    builder.command("!!ez rcon auto", rcon_auto)
    builder.command("!!ez rcon status", rcon_status)

    # 假人过滤命令
    builder.command("!!ez bot toggle", toggle_bot_filter)
    builder.command("!!ez bot add <prefix>", add_bot_prefix)
    builder.command("!!ez bot remove <prefix>", remove_bot_prefix)
    builder.command("!!ez bot list", list_bot_prefixes)
    
    # 注册到服务器
    builder.register(server)
    server.logger.info("命令注册完成")
    server.register_help_message('!!ez', '显示EasyBot的帮助菜单')



async def bind(source: CommandSource):
    if source.is_console:
        source.reply("§c这个命令不能在控制台使用!")
        return

    bind_data = await wsc.get_social_account(source.player)
    if bind_data["uuid"] is None or bind_data["uuid"] == "":
        code = await wsc.start_bind(source.player)
        message: str = get_config()["message"]["start_bind"]
        message = message.replace("#code", code["code"])
        message = message.replace("#time", code["time"])
        source.reply(message)
    else:
        source.reply(
            f"§c你已经绑定了账号, ({bind_data['name']}/{bind_data['uuid']}/时间:{bind_data['time']}/{bind_data['platform']})"
        )

async def reload(source: CommandSource):
    """重载插件配置"""
    if not source.has_permission(3):
        source.reply(f"§c你没有权限使用这个命令!")
        return
    
    global wsc, server_interface
    try:
        # 加载配置
        load_config(server_interface)
        
        # 重新初始化WebSocket客户端
        wsc = await initialize_websocket_client(server_interface)
        
        source.reply("§a插件重载成功!")
    except Exception as e:
        server_interface.logger.error(f"重载时出错: {str(e)}")
        server.logger.debug("\n{traceback.format_exc()}")
        source.reply(f"§c重载失败: {str(e)}")

async def say(source: CommandSource, context: CommandContext):
    name = "CONSOLE"
    if source.is_player:
        name = source.player
    await wsc.push_message(name, context["message"], True)
    source.reply("§a消息已发送: §f" + context["message"])

async def rcon_auto(source: CommandSource):
    """自动配置RCON"""
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    from easybot_mcdr.rcon_config import check_rcon_config, auto_configure_rcon
    server = source.get_server()
    status = check_rcon_config(server)
    if status["rcon_enabled"] and server.is_rcon_running():
        source.reply(f"§aRCON 已配置并运行中! (端口: {status['rcon_port']})")
        return
    source.reply("§e正在自动配置RCON...")
    success = auto_configure_rcon(server)
    if success:
        new_status = check_rcon_config(server)
        if server.is_rcon_running():
            source.reply(f"§aRCON 配置已同步! (端口: {new_status['rcon_port']})")
        else:
            source.reply(f"§aRCON 自动配置完成! 端口: §f{new_status['rcon_port']}")
            source.reply("§e请重启服务器生效。")
    else:
        source.reply("§cRCON 自动配置失败，请检查日志。")

async def rcon_status(source: CommandSource):
    """查看RCON状态"""
    from easybot_mcdr.rcon_config import check_rcon_config, test_rcon_connection
    status = check_rcon_config(source.get_server())
    running = test_rcon_connection(source.get_server())
    port_ok = "§a是" if not status["port_mismatch"] else f"§c否 (MCDR:{status['rcon_port']} vs 服务端:{status['server_rcon_port']})"
    lines = [
        '--------§a RCON 状态 §r--------',
        f'§bMCDR RCON: §f{"§a启用" if status["mcdr_rcon_enabled"] else "§c禁用"}',
        f'§b服务端 RCON: §f{"§a启用" if status["server_rcon_enabled"] else "§c禁用"}',
        f'§bRCON 端口: §f{status["rcon_port"]}',
        f'§b端口一致: §f{port_ok}',
        f'§bRCON 连接: §f{"§a正常" if running else "§c未连接"}',
        '---------------------------------------------'
    ]
    if status["needs_config"]:
        lines.append("§e提示: 使用 §b!!ez rcon auto §e自动配置RCON")
    for line in lines:
        source.reply(line)

async def toggle_bot_filter(source: CommandSource):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    config = get_config()
    bot_filter = config.setdefault("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    bot_filter["enabled"] = not bot_filter.get("enabled", True)
    save_config(server_interface)
    state = "启用" if bot_filter["enabled"] else "禁用"
    source.reply(f"§a假人过滤已{state}")

async def add_bot_prefix(source: CommandSource, context: CommandContext):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    prefix = context["prefix"]
    config = get_config()
    bot_filter = config.setdefault("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    prefixes = bot_filter.setdefault("prefixes", ["Bot_", "BOT_", "bot_"])
    if prefix not in prefixes:
        prefixes.append(prefix)
        save_config(server_interface)
        source.reply(f"§a已添加假人前缀: {prefix}")
    else:
        source.reply(f"§c前缀 {prefix} 已存在!")

async def remove_bot_prefix(source: CommandSource, context: CommandContext):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    prefix = context["prefix"]
    config = get_config()
    bot_filter = config.setdefault("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    prefixes = bot_filter.setdefault("prefixes", ["Bot_", "BOT_", "bot_"])
    if prefix in prefixes:
        prefixes.remove(prefix)
        save_config(server_interface)
        source.reply(f"§a已移除假人前缀: {prefix}")
    else:
        source.reply(f"§c前缀 {prefix} 不存在!")

async def list_bot_prefixes(source: CommandSource):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    prefixes = bot_filter.get("prefixes", ["Bot_", "BOT_", "bot_"])
    state = "启用" if bot_filter.get("enabled", True) else "禁用"
    source.reply(f"§a假人过滤状态: {state}")
    source.reply("§a假人前缀列表: " + ", ".join(prefixes) if prefixes else "§c无前缀")


# 新增：定期UUID同步检查函数
@new_thread("UUID_Sync_Check")
def periodic_uuid_check():
    """定期检查和修复UUID不一致问题"""
    import time
    from easybot_mcdr.api.player import online_players, uuid_map, generate_offline_uuid, update_player_uuid
    from easybot_mcdr.impl.get_server_info import get_online_mode
    
    while True:
        try:
            time.sleep(30)  # 每30秒检查一次
            
            # 安全获取在线模式状态，避免直接使用未初始化的全局变量
            try:
                online_mode = get_online_mode()
            except (NameError, AttributeError):
                server = ServerInterface.get_instance()
                server.logger.warning("无法获取在线模式状态，使用默认值(False)")
                online_mode = False
            
            if not online_mode:
                server = ServerInterface.get_instance()
                for player in list(online_players.keys()):
                    current_uuid = online_players[player].uuid
                    expected_uuid = generate_offline_uuid(player)
                    
                    if current_uuid != expected_uuid and current_uuid in ["unknown", "", None]:
                        server.logger.warning(f"检测到玩家 {player} UUID不一致，正在修复...")
                        update_player_uuid(player, expected_uuid)
                        
        except Exception as e:
            server = ServerInterface.get_instance()
            server.logger.error(f"UUID同步检查出错: {e}")
            server.logger.debug("\n{traceback.format_exc()}")
