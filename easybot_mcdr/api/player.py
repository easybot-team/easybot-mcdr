import json
from typing import List
from mcdreforged.api.all import *
import re
import requests
import hashlib
from easybot_mcdr.impl.get_server_info import get_online_mode

class PlayerInfo:
    ip: str
    name: str
    uuid: str

    def __init__(self, ip: str, name: str, uuid: str):
        self.ip = ip
        self.name = name
        self.uuid = uuid

online_players = {} 
uuid_map = {}
cached_data = {} 

# UUID 锚点 session 表：uuid -> {"real_name": str, "uuid": str, "aliases": set}
# join 时建立，left 时清除；名字只用于显示，UUID 才是匹配绑定的钥匙
player_sessions = {}
# 名字 -> uuid 的反查索引（包含真实名和别名），用于把改写后的名字还原回锚点
name_to_uuid = {}

def get_data_map():
    global online_players, uuid_map, cached_data
    return {
        "online_players": online_players,
        "uuid_map": uuid_map,
        "cache": cached_data
    }

def load_data_map(data: dict):
    global online_players, uuid_map, cached_data
    online_players = data["online_players"]
    uuid_map = data["uuid_map"]
    cached_data = data["cache"]

def init_player_api(server: PluginServerInterface, old):
    reload_player_api(old)
    server.register_event_listener("mcdr.server_stop", on_server_stop, 1)
    server.register_event_listener("mcdr.player_joined", on_player_joined, 1)
    server.register_event_listener("mcdr.player_left", on_player_left, 1)
    server.register_event_listener("mcdr.general_info", on_stdout, 1)

    builder = SimpleCommandBuilder()
    builder.command("!!d list", list_player)
    builder.register(server)
    pass

def list_player(sender: CommandSource):
    if not sender.has_permission(3):
        sender.reply("§c你没有权限使用这个命令!")
    sender.reply("§a在线玩家列表: ")

    for player in online_players:
        sender.reply(f"§a{player} §eIP:{online_players[player].ip} §6UUID:{online_players[player].uuid}")

    return True

def on_stdout(server, info: Info):
    raw = info.raw_content
    # 正则解析 UUID, 构建UUIDMap
    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw
    ):
        name = match.group(1)
        uuid = match.group(2).lower()
        uuid_map[name] = uuid
        logger = ServerInterface.get_instance().logger
        logger.info("已缓存玩家 %s 的UUID: %s" % (name, uuid))
    pass

def reload_player_api(old):
    if old is not None:
        load_data_map(old)
    # 热重载后从 online_players 重建 session 锚点，保证在线玩家身份不丢
    _rebuild_sessions_from_online()

def on_server_stop(server, return_code):
    global online_players
    global uuid_map
    global cached_data
    online_players = {}
    uuid_map = {}
    cached_data = {}
    clear_sessions()


def is_bot_player(player: str) -> bool:
    """Check if player is a bot by name prefix"""
    return player.startswith(('Bot_', 'BOT_', 'bot_'))

def generate_offline_uuid(player_name: str) -> str:
    """生成离线模式UUID（符合Mojang规范）"""
    digest = hashlib.md5(b"OfflinePlayer:" + player_name.encode('utf-8')).digest()
    namespace = bytearray(digest)
    # 设置版本位 (第6字节的高4位为0011)
    namespace[6] = (namespace[6] & 0x0f) | 0x30  # Version 3
    # 设置变体位 (第8字节的高2位为10)
    namespace[8] = (namespace[8] & 0x3f) | 0x80  # Variant RFC 4122
    # 转换为UUID字符串
    return '-'.join([
        bytes(namespace[0:4]).hex(),
        bytes(namespace[4:6]).hex(),
        bytes(namespace[6:8]).hex(),
        bytes(namespace[8:10]).hex(),
        bytes(namespace[10:16]).hex()
    ])

def update_player_uuid(player: str, new_uuid: str):
    """更新玩家UUID并同步到所有缓存"""
    global online_players, uuid_map, cached_data
    
    # 更新UUID映射
    old_uuid = uuid_map.get(player)
    uuid_map[player] = new_uuid
    
    # 更新在线玩家信息
    if player in online_players:
        online_players[player].uuid = new_uuid
    
    # 更新缓存信息
    if player in cached_data:
        cached_data[player].uuid = new_uuid
    
    logger = ServerInterface.get_instance().logger
    if old_uuid != new_uuid:
        logger.info(f"玩家 {player} 的UUID已更新: {old_uuid} -> {new_uuid}")


# ==================== UUID 锚点 session 管理 ====================

def register_session(real_name: str, uuid: str):
    """join 时建立 UUID 锚点 session。真实名 + UUID 一经锚定，后续显示名变化不影响匹配。"""
    global player_sessions, name_to_uuid
    if not real_name or not uuid or uuid == "unknown":
        return
    uuid = uuid.lower()
    session = {
        "real_name": real_name,
        "uuid": uuid,
        "aliases": set()
    }
    player_sessions[uuid] = session
    name_to_uuid[real_name] = uuid

def remove_session(uuid: str):
    """left 时清除 session 及其名字索引"""
    global player_sessions, name_to_uuid
    if not uuid:
        return
    uuid = uuid.lower()
    session = player_sessions.pop(uuid, None)
    if session is None:
        return
    name_to_uuid.pop(session["real_name"], None)
    for alias in session["aliases"]:
        if name_to_uuid.get(alias) == uuid:
            name_to_uuid.pop(alias, None)

def add_alias(uuid: str, alias: str):
    """记录某个 UUID 的别名（模组改写后的显示名），用于反查还原"""
    global player_sessions, name_to_uuid
    if not alias:
        return
    uuid = uuid.lower() if uuid else ""
    alias = alias.strip()
    if not alias or not uuid or uuid not in player_sessions:
        return
    session = player_sessions[uuid]
    if alias == session["real_name"]:
        return
    session["aliases"].add(alias)
    if alias not in name_to_uuid:
        name_to_uuid[alias] = uuid

def resolve_player(raw_name: str):
    """
    反查：把任意名字（含模组改写后的显示名）还原为 join 时锚定的真实名和 UUID。
    返回 (real_name, uuid)；查不到返回 (raw_name, None)。
    这是让插件对任意改名方式免疫的核心。
    """
    if not raw_name:
        return (raw_name, None)
    raw = raw_name.strip()
    if not raw:
        return (raw_name, None)
    # 1. 名字索引精确命中（真实名或已记录别名）
    uuid = name_to_uuid.get(raw)
    if uuid and uuid in player_sessions:
        return (player_sessions[uuid]["real_name"], uuid)
    # 2. 在线玩家精确匹配
    if raw in online_players:
        u = online_players[raw].uuid
        if u and u != "unknown":
            return (raw, u)
    # 3. 子串匹配：改写后的名字通常包含真实名（如 [VIP]Steve 含 Steve）
    for online_name in online_players:
        if online_name and len(online_name) >= 2 and online_name in raw:
            u = online_players[online_name].uuid
            if u and u != "unknown":
                return (online_name, u)
    # 4. 反向子串：真实名包含解析名（少见，兜底）
    for online_name in online_players:
        if raw and len(raw) >= 2 and raw in online_name:
            u = online_players[online_name].uuid
            if u and u != "unknown":
                return (online_name, u)
    # 5. 查不到，返回原名与空 UUID
    return (raw, None)

def get_session_by_uuid(uuid: str):
    uuid = uuid.lower() if uuid else ""
    return player_sessions.get(uuid)

def _rebuild_sessions_from_online():
    """从 online_players 重建 session 锚点（用于热重载后恢复在线玩家锚点）"""
    global player_sessions, name_to_uuid
    player_sessions = {}
    name_to_uuid = {}
    for name, info in online_players.items():
        if info.uuid and info.uuid != "unknown":
            register_session(name, info.uuid)

def clear_sessions():
    """服务器停止时清空所有 session"""
    global player_sessions, name_to_uuid
    player_sessions = {}
    name_to_uuid = {}

def on_player_joined(server, player, info: Info):
    logger = ServerInterface.get_instance().logger

    # Skip bot players
    if is_bot_player(player):
        logger.info(f"检测到假人玩家 {player}，跳过数据处理")
        return

    # 统一的UUID获取逻辑
    uuid = uuid_map.get(player)
    if uuid is None:
        if get_online_mode():
            try:
                response = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{player}")
                response.raise_for_status()
                id = json.loads(response.text)['id']
                uuid = f"{id[:8]}-{id[8:12]}-{id[12:16]}-{id[16:20]}-{id[20:]}"
            except Exception as e:
                logger.warning(f"获取玩家 {player} 正版UUID失败: {e}")
                uuid = generate_offline_uuid(player)  # 降级到离线UUID
        else:
            uuid = generate_offline_uuid(player)  # 离线模式直接生成UUID

        # 更新UUID映射
        update_player_uuid(player, uuid)

    # 获取IP地址
    ip = "127.0.0.1"
    if match := re.search(r'\d+\.\d+\.\d+\.\d+', info.raw_content):
        ip = match.group()

    player_info = PlayerInfo(ip, player, uuid)
    online_players[player] = player_info
    cached_data[player] = player_info

    # 建立 UUID 锚点 session：真实名 + UUID 一经锚定，后续显示名变化不影响匹配
    register_session(player, uuid)

    logger.info(f"玩家 {player} 加入成功: UUID={uuid}, IP={ip}")

def build_player_info(player: str):
    # 先尝试直接命中缓存/在线表
    if not check_cache(player):
        if player in online_players:
            return {
                "player_name": player,
                "player_uuid": online_players[player].uuid,
                "ip": online_players[player].ip,
                "skin_url": "",
                "bedrock": False
            }
        # 直接命中失败：通过 UUID 锚点 session 反查真实名
        real_name, uuid = resolve_player(player)
        if uuid and real_name in online_players:
            return {
                "player_name": real_name,
                "player_uuid": uuid,
                "ip": online_players[real_name].ip,
                "skin_url": "",
                "bedrock": False
            }
        return None

    return {
        "player_name": player,
        "player_uuid": cached_data[player].uuid,
        "ip": cached_data[player].ip,
        "skin_url": "",
        "bedrock": False
    }

def on_player_left(server, player):
    logger = ServerInterface.get_instance().logger
    if is_bot_player(player):
        logger.info(f"检测到假人玩家 {player} 退出，跳过数据处理")
        return

    # 先按真实名取 UUID 清除 session，再移除在线记录
    info = online_players.get(player)
    if info and info.uuid:
        remove_session(info.uuid)
    if player in online_players:
        online_players.pop(player)

def check_cache(player:str) -> bool:
    return player in cached_data


def check_online(player: str) -> bool:
    """Check a player is online"""
    return player in online_players


def get_player_list():
    """Get all online player list"""
    return online_players.copy()