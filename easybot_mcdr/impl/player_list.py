import asyncio
import time
import requests
from easybot_mcdr.impl.get_server_info import get_online_mode, get_skins_restorer
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

# Mojang 正版检测缓存: {name: (is_premium, timestamp)}
_premium_cache = {}
_PREMIUM_CACHE_TTL = 3600  # 1小时


def _check_premium_sync(name: str) -> bool:
    """同步查询 Mojang API 判断是否为正版账户"""
    try:
        resp = requests.get(
            f"https://api.mojang.com/users/profiles/minecraft/{name}",
            timeout=5
        )
        return resp.status_code == 200
    except Exception:
        return False


async def check_premium(name: str) -> bool:
    """异步查询 Mojang API，带缓存"""
    now = time.time()
    if name in _premium_cache:
        is_premium, ts = _premium_cache[name]
        if now - ts < _PREMIUM_CACHE_TTL:
            return is_premium
    loop = asyncio.get_event_loop()
    is_premium = await loop.run_in_executor(None, _check_premium_sync, name)
    _premium_cache[name] = (is_premium, now)
    return is_premium


def _get_sr_skin(name: str) -> str:
    """从 SkinsRestorer SQLite 数据库读取皮肤 URL"""
    try:
        from mcdreforged.api.all import ServerInterface
        server = ServerInterface.get_instance()
        working_dir = server.get_mcdr_config()["working_directory"]
        plugins_dir = os.path.join(working_dir, "plugins")

        # 新版路径
        db_path = os.path.join(plugins_dir, "SkinsRestorer", "skins", "skins.db")
        if not os.path.isfile(db_path):
            # 旧版路径
            db_path = os.path.join(plugins_dir, "SkinsRestorer", "Skins.db")
        if not os.path.isfile(db_path):
            return ""

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        skin_url = ""

        # 尝试新版表 sr_skins
        if "sr_skins" in tables:
            cursor.execute("PRAGMA table_info(sr_skins)")
            columns = [col[1] for col in cursor.fetchall()]

            nick_col = next((c for c in columns if c in ("nick", "name", "player")), None)
            skin_col = next((c for c in columns if c in ("skin", "value", "texture", "url")), None)

            if nick_col and skin_col:
                cursor.execute(f"SELECT `{skin_col}` FROM sr_skins WHERE `{nick_col}` = ?", (name,))
                row = cursor.fetchone()
                if row and row[0]:
                    val = str(row[0])
                    if val.startswith("http"):
                        skin_url = val
                    elif len(val) > 100:
                        # base64 编码的 textures JSON
                        try:
                            decoded = base64.b64decode(val).decode("utf-8")
                            data = json.loads(decoded)
                            skin_url = data.get("textures", {}).get("SKIN", {}).get("url", "")
                        except Exception:
                            pass

        # 尝试旧版表 skins
        if not skin_url and "skins" in tables:
            cursor.execute("PRAGMA table_info(skins)")
            columns = [col[1] for col in cursor.fetchall()]

            name_col = next((c for c in columns if c in ("name", "nick", "player")), None)
            value_col = next((c for c in columns if c in ("value", "skin", "texture", "url")), None)

            if name_col and value_col:
                cursor.execute(f"SELECT `{value_col}` FROM skins WHERE `{name_col}` = ?", (name,))
                row = cursor.fetchone()
                if row and row[0]:
                    val = str(row[0])
                    if val.startswith("http"):
                        skin_url = val
                    elif len(val) > 100:
                        try:
                            decoded = base64.b64decode(val).decode("utf-8")
                            data = json.loads(decoded)
                            skin_url = data.get("textures", {}).get("SKIN", {}).get("url", "")
                        except Exception:
                            pass

        conn.close()

        if skin_url:
            server.logger.info(f"[EasyBot-SKIN] SR 找到皮肤: {name} -> {skin_url[:60]}")
        return skin_url

    except Exception as e:
        try:
            from mcdreforged.api.all import ServerInterface
            ServerInterface.get_instance().logger.debug(f"[EasyBot-SKIN] SR 读取失败: {e}")
        except Exception:
            pass
        return ""


async def try_get_skin(name, uuid=""):
    online = get_online_mode()
    has_sr = get_skins_restorer()

    # SkinsRestorer: 从数据库读取自定义皮肤
    if has_sr:
        sr_skin = _get_sr_skin(name)
        if sr_skin:
            return sr_skin
        # 数据库没找到，fallback
        return f"https://mineskin.eu/download/{name}"

    if online:
        return f"https://mineskin.eu/download/{name}"

    # 离线模式无皮肤站: 查询 Mojang 判断是否正版
    is_premium = await check_premium(name)
    if is_premium:
        # 正版账户: mineskin 能获取到正确皮肤
        return f"https://mineskin.eu/download/{name}"

    # 非正版: 使用 mc-heads.net 头像
    if uuid:
        return f"https://mc-heads.net/skin/{uuid}"
    return ""

@EasyBotWsClient.listen_exec_op("PLAYER_LIST")
async def on_get_player_list(ctx: ExecContext, data:dict, _):
    logger = ServerInterface.get_instance().logger
    from easybot_mcdr.api.player import get_player_list
    online_list = get_player_list()
    list = []
    for player in online_list:
        skin_url = await try_get_skin(player, online_list[player].uuid)
        list.append({
            "player_name": player,
            "player_uuid": online_list[player].uuid,
            "ip": online_list[player].ip,
            "bedrock": False,
            "skin_url": skin_url
        })
    await ctx.callback({
        "list": list
    })