import os
import re
import glob
from easybot_mcdr.meta import get_plugin_version
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

# 初始化在线模式变量，默认为False（离线模式）
is_online_mode = False
has_skins_restorer = False

@EasyBotWsClient.listen_exec_op("GET_SERVER_INFO")
async def exec_get_server_info(ctx: ExecContext, data:dict, _):
    global is_online_mode, has_skins_restorer
    server = ServerInterface.get_instance()
    working_directory = server.get_mcdr_config()["working_directory"]
    properties_path = os.path.join(working_directory, "server.properties")
    online_mode = False
    with open(properties_path, "r", encoding='utf-8') as f:
        online_mode = re.search(r"online-mode=(.*)", f.read()).group(1)
        online_mode = str(online_mode).lower().strip() == "true"

    # 检测 SkinsRestorer 插件
    plugins_dir = os.path.join(working_directory, "plugins")
    sr_found = bool(glob.glob(os.path.join(plugins_dir, "SkinsRestorer*.jar")))
    has_skins_restorer = sr_found

    try:
        # 检测 PAPI 支持 (仅 Bukkit 系列)
        try:
            from mcdreforged.handler.impl.bukkit_handler import BukkitHandler
            is_bukkit = isinstance(server.get_server_handler(), BukkitHandler)
        except Exception:
            is_bukkit = False

        packet = {
            "server_name": "mcdr",
            "server_version": f"MCDR {server.get_plugin_metadata('mcdreforged').version}",
            "plugin_version": get_plugin_version(),
            "is_papi_supported": is_bukkit,
            "is_command_supported": True,
            "has_geyser": False,
            "has_skins_restorer": sr_found,
            "is_online_mode": online_mode
        }
        # 确保所有字符串都是UTF-8编码
        packet = {k: v.encode('utf-8').decode('utf-8') if isinstance(v, str) else v
                 for k, v in packet.items()}
    except Exception as e:
        server.logger.error(f"构建服务器信息包时出错: {str(e)}")
        raise
    is_online_mode = online_mode
    await ctx.callback(packet)
    ServerInterface.get_instance().logger.info(f"{packet['server_version']} 正版验证: {'是' if online_mode else '否'} SkinsRestorer: {'是' if sr_found else '否'}")
    return

def get_online_mode():
    """
    读取server.properties文件获取服务器在线模式设置
    直接返回解析结果，并更新全局变量
    """
    global is_online_mode
    try:
        server = ServerInterface.get_instance()
        working_directory = server.get_mcdr_config()["working_directory"]
        properties_path = os.path.join(working_directory, "server.properties")

        # 直接读取并解析文件，与exec_get_server_info中的逻辑类似
        with open(properties_path, "r", encoding='utf-8') as f:
            content = f.read()
            match = re.search(r"online-mode=(.*)", content)
            if match:
                online_mode = str(match.group(1)).lower().strip() == "true"
                # 更新全局变量
                is_online_mode = online_mode
                return online_mode
            else:
                server.logger.warning("在server.properties中未找到online-mode配置，默认为离线模式")
                is_online_mode = False
                return False
    except Exception as e:
        server = ServerInterface.get_instance()
        server.logger.error(f"读取服务器在线模式时出错: {str(e)}")
        # 出错时返回当前全局变量的值
        return is_online_mode


def get_skins_restorer() -> bool:
    """返回 SkinsRestorer 插件是否已检测到"""
    return has_skins_restorer

@new_thread("EasyBot-GetPlayers")
def get_online_players(server: PluginServerInterface):
    try:
        players = server.get_online_players()
        server.logger.debug(f"获取在线玩家列表: {players}")
        return {
            "success": True,
            "players": players,
            "count": len(players)
        }
    except Exception as e:
        server.logger.warning(f"获取在线玩家列表失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }