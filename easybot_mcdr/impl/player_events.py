import asyncio
import re
import time
from mcdreforged.api.all import *


async def on_player_joined(server: PluginServerInterface, player: str, info: Info):
    from easybot_mcdr.main import wsc, is_bot_player, kick_map
    from easybot_mcdr.api.player import cached_data
    from easybot_mcdr.config import get_config

    try:
        config = get_config()
        bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
        server.logger.debug(f"假人过滤配置: enabled={bot_filter['enabled']}, prefixes={bot_filter['prefixes']}")

        if is_bot_player(player):
            ip = "unknown"
            if match := re.search(r'\d+\.\d+\.\d+\.\d+', info.raw_content):
                ip = match.group()
            player_info = cached_data.get(player)
            uuid = player_info.uuid if player_info else "unknown"
            server.logger.info(f"检测到假人 {player} (匹配前缀: {bot_filter['prefixes']}), UUID={uuid}, IP={ip}")
            return

        player_info = await wsc.report_player(player)
        if player_info is None:
            server.logger.warning(f"玩家 {player} 的信息未准备好，可能是数据同步延迟")
            return
        server.logger.info(f"玩家 {player} 已加入并缓存: UUID={player_info['player_uuid']}, IP={player_info['ip']}")
        res = await wsc.login(player)
        if res is None:
            server.logger.error(f"玩家 {player} 登录验证返回空响应")
            return
        if res.get("kick", False):
            kick_msg = res.get("kick_message", "验证失败")
            server.logger.info(f"检测到玩家 {player} 需要被踢出，等待加载延迟...")
            kick_map[player] = time.time()
            if player not in kick_map:
                kick_map[player] = time.time()

            server.tell(player, f"§c[EasyBot] 验证未通过: {kick_msg}")
            server.tell(player, "§c[EasyBot] 您将在 5 秒后被移出服务器，请按照提示操作。")

            kick_delay = get_config().get("kick_delay_seconds", 5)
            await asyncio.sleep(kick_delay)
            _push_kick(player, kick_msg)
            return

        if player in kick_map:
            kick_map.pop(player)

        await wsc.push_enter(player)

        # 检查 RCON 配置并提示管理员
        notify_rcon_not_configured(server, player)

        # 检查编码配置是否需要重启生效
        notify_encoding_config_reload(server, player)

    except Exception as e:
        server.logger.error(f"处理玩家 {player} 加入时出错: {e}")
        import traceback
        server.logger.debug(f"{traceback.format_exc()}")


async def on_player_left(server: PluginServerInterface, player: str):
    from easybot_mcdr.main import wsc, is_bot_player, kick_map, exit_reported_at, debounce_time
    from easybot_mcdr.config import get_config

    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    server.logger.debug(f"处理玩家退出事件: {player}, 假人过滤状态: enabled={bot_filter['enabled']}")

    if player in kick_map:
        if time.time() - kick_map[player] < 15:
            server.logger.debug(f"玩家 {player} 是被踢出的，跳过处理")
            return
        else:
            kick_map.pop(player, None)

    if is_bot_player(player):
        server.logger.info(f"过滤假人 {player} 的退出事件 (匹配前缀: {bot_filter['prefixes']})")
        return

    now = time.time()
    last = exit_reported_at.get(player, 0)
    if now - last < 2.0:
        server.logger.debug(f"忽略重复退出上报: {player}")
        return
    exit_reported_at[player] = now

    server.logger.debug(f"正常玩家 {player} 退出事件处理")
    await wsc.push_exit(player)


async def _report_player_exit(server: PluginServerInterface, name: str):
    from easybot_mcdr.main import wsc, is_bot_player, kick_map, exit_reported_at, debounce_time

    if name in kick_map:
        if time.time() - kick_map[name] < 15:
            server.logger.debug(f"玩家 {name} 是被踢出的，退出事件上报已跳过")
            return
        else:
            kick_map.pop(name, None)

    if is_bot_player(name):
        server.logger.info(f"过滤假人 {name} 的退出事件")
        return

    now = time.time()
    last = exit_reported_at.get(name, 0)
    if now - last < debounce_time:
        server.logger.debug(f"忽略重复退出上报: {name}")
        return
    exit_reported_at[name] = now

    try:
        await wsc.push_exit(name)
        server.logger.debug(f"已上报玩家退出: {name}")
    except Exception as e:
        server.logger.error(f"上报玩家 {name} 退出失败: {e}")
        import traceback
        server.logger.debug(f"{traceback.format_exc()}")


async def on_info(server, info: Info):
    raw = info.raw_content
    from easybot_mcdr.main import wsc, is_bot_player

    if match := re.search(
        r"UUID of player ([\w.]+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw,
    ):
        name = match.group(1)
        uuid = match.group(2).lower()

        if not is_bot_player(name):
            from easybot_mcdr.api.player import update_player_uuid
            update_player_uuid(name, uuid)
            server.logger.info(f"从服务器获取到玩家 {name} 的正版UUID: {uuid}")
        return

    m_join_pref = re.search(r"^\[[^\]]+\](?P<name>[\w.]+) joined the game$", raw)
    m_join_plain = re.search(r"^(?P<name>[\w.]+) joined the game$", raw)
    if m_join_pref or m_join_plain:
        name = (m_join_pref or m_join_plain).group('name')

        if is_bot_player(name):
            server.logger.info(f"检测到假人 {name}，跳过UUID处理")
            return

        from easybot_mcdr.api.player import uuid_map, generate_offline_uuid, update_player_uuid, online_players, cached_data, PlayerInfo
        from easybot_mcdr.impl.get_server_info import get_online_mode

        current_uuid = uuid_map.get(name)
        if not current_uuid or current_uuid == "unknown":
            if not get_online_mode():
                correct_uuid = generate_offline_uuid(name)
                update_player_uuid(name, correct_uuid)
                server.logger.info(f"修正玩家 {name} 的离线UUID: {correct_uuid}")

        try:
            ip = "127.0.0.1"
            if match_ip := re.search(r"\d+\.\d+\.\d+\.\d+", raw):
                ip = match_ip.group()
            if name not in online_players:
                online_players[name] = PlayerInfo(ip, name, uuid_map.get(name, "unknown"))
            cached_data[name] = online_players[name]
        except Exception as e:
            server.logger.warning(f"写入玩家 {name} 本地缓存失败: {e}")

        from easybot_mcdr.utils import is_white_list_enable
        if is_white_list_enable():
            try:
                bind_info = await wsc.get_social_account(name)
                if bind_info and bind_info.get("uuid"):
                    server.execute(f"whitelist add {name}")
            except Exception as e:
                server.logger.error(f"获取玩家 {name} 绑定信息失败: {str(e)}")
                import traceback
                server.logger.debug(f"{traceback.format_exc()}")
        return

    m_quit = re.search(r"(?:\[[^\]]+\])?(?P<name>[\w.]+) left the game", raw)
    if m_quit:
        name = m_quit.group('name')
        server.logger.debug(f"检测到退出行，解析玩家: {name} | 原始: {raw}")
        await _report_player_exit(server, name)
        return

    m_lost = re.search(r"(?:\[[^\]]+\])?(?P<name>[\w.]+) lost connection:\s*", raw)
    if m_lost:
        name = m_lost.group('name')
        server.logger.debug(f"检测到断开行，解析玩家: {name} | 原始: {raw}")
        await _report_player_exit(server, name)
        return


async def on_player_death(server: PluginServerInterface, player: str, killer: str = None):
    from easybot_mcdr.main import is_bot_player
    from easybot_mcdr.config import get_config

    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    server.logger.debug(f"处理玩家死亡事件: {player}, 假人过滤状态: enabled={bot_filter['enabled']}")

    if is_bot_player(player):
        server.logger.info(f"过滤假人 {player} 的死亡事件 (匹配前缀: {bot_filter['prefixes']})")
        return
    server.logger.debug(f"正常玩家 {player} 死亡事件处理")


def _push_kick(player: str, reason: str):
    from easybot_mcdr.main import kick_map
    if reason is None or reason.strip() == "":
        reason = "你已被踢出服务器"
    server = ServerInterface.get_instance()
    kick_map[player] = time.time()
    if not server.is_rcon_running():
        server.logger.error("你的服务器RCON当前并未运行,踢出玩家的原因无法显示多行。")
        server.logger.error(f"即将踢出玩家 {player} 并且只显示踢出原因的第一行!")
        first_line = reason.split("\n")[0]
        server.execute(f"kick {player} {first_line}")
        return
    server.rcon_query(f"kick {player} {reason}")
    kick_map[player] = time.time()


# RCON 未配置提示冷却: {player: last_notify_time}
_rcon_notify_cooldown = {}
_RCON_NOTIFY_INTERVAL = 300  # 5分钟内不重复提示同一玩家


def notify_rcon_not_configured(server: PluginServerInterface, player: str):
    """当 RCON 未配置时，在游戏内提示管理员"""
    now = time.time()
    last = _rcon_notify_cooldown.get(player, 0)
    if now - last < _RCON_NOTIFY_INTERVAL:
        return

    if server.is_rcon_running():
        return

    from easybot_mcdr.rcon_config import check_rcon_config
    status = check_rcon_config(server)
    if not status["needs_config"]:
        return

    # 只通知权限等级 >= 2 的玩家（管理员）
    try:
        perm_level = server.get_permission_level(player)
        if perm_level >= 2:
            server.tell(player, "§e[EasyBot] §cRCON 未配置! 命令执行、玩家皮肤获取等功能受限。")
            server.tell(player, "§e[EasyBot] 使用 §b!!ez rcon auto §e自动配置RCON")
            _rcon_notify_cooldown[player] = now
    except Exception:
        pass


# 编码配置重载提示冷却: {player: last_notify_time}
_encoding_notify_cooldown = {}
_ENCODING_NOTIFY_INTERVAL = 300  # 5分钟内不重复提示同一玩家


def notify_encoding_config_reload(server: PluginServerInterface, player: str):
    """当编码配置被修改时，在游戏内提示管理员执行 reload"""
    # 检查是否有编码配置需要重载
    if not getattr(server, '_easybot_encoding_fixed', False):
        return

    now = time.time()
    last = _encoding_notify_cooldown.get(player, 0)
    if now - last < _ENCODING_NOTIFY_INTERVAL:
        return

    # 只通知权限等级 >= 2 的玩家（管理员）
    try:
        perm_level = server.get_permission_level(player)
        if perm_level >= 2:
            server.tell(player, "§e[EasyBot] §c已自动修改编码配置来防止可能出现的乱码情况。")
            server.tell(player, "§e[EasyBot] 请执行 §b!!MCDR reload config §e使配置生效")
            _encoding_notify_cooldown[player] = now
    except Exception:
        pass
