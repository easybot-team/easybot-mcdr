import asyncio
import re
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

# 缓存: 服务端是否支持 PAPI (Bukkit 系列)
_papi_supported_cache = None


def _is_bukkit_server() -> bool:
    """检测当前服务端是否为 Bukkit 系列 (Spigot/Paper 等)"""
    global _papi_supported_cache
    if _papi_supported_cache is not None:
        return _papi_supported_cache

    try:
        server = ServerInterface.get_instance()
        handler = server.get_server_handler()
        # BukkitHandler 及其子类 (Spigot, Paper 等) 都继承自 BukkitHandler
        from mcdreforged.handler.impl.bukkit_handler import BukkitHandler
        _papi_supported_cache = isinstance(handler, BukkitHandler)
    except Exception:
        _papi_supported_cache = False

    return _papi_supported_cache


def get_placeholders(text: str) -> list[str]:
    return re.findall(r"%\w+%", text)


def _local_replace(player: str, text: str) -> str:
    """
    本地基础变量替换 (所有服务端类型通用)
    支持的变量:
      %player_name%  - 玩家名
      %player_uuid%  - 玩家 UUID
      %player_ip%    - 玩家 IP
    """
    server = ServerInterface.get_instance()
    logger = server.logger
    query_text = text

    # 从玩家 API 获取数据
    try:
        from easybot_mcdr.api.player import online_players, uuid_map
        player_info = online_players.get(player)
        uuid = uuid_map.get(player, "unknown")
        ip = player_info.ip if player_info else "unknown"
    except Exception:
        uuid = "unknown"
        ip = "unknown"

    for placeholder in get_placeholders(query_text):
        lower = placeholder.lower()
        if lower == "%player_name%":
            query_text = query_text.replace(placeholder, player)
        elif lower == "%player_uuid%":
            query_text = query_text.replace(placeholder, uuid)
        elif lower == "%player_ip%":
            query_text = query_text.replace(placeholder, ip)
        else:
            logger.warning(f"不支持的变量: {placeholder} [仅支持基础变量: player_name, player_uuid, player_ip]")
    return query_text


async def run_placeholder(player: str, text: str, use_rcon: bool = True) -> str:
    """
    占位符解析:
    - Bukkit 服务端: 优先通过 RCON 调用 PAPI (papi parse <player> "<text>")
    - 非 Bukkit 服务端: PAPI 不可用, 使用本地基础替换
    """
    server = ServerInterface.get_instance()
    logger = server.logger

    # 检测服务端类型
    if not _is_bukkit_server():
        logger.debug(f"PAPI 不可用 (非 Bukkit 服务端), 使用本地替换: {text}")
        return _local_replace(player, text)

    # Bukkit 服务端: 优先通过 RCON 调用 PAPI
    if use_rcon and server.is_rcon_running():
        cmd = f'papi parse {player} "{text}"'
        try:
            resp = server.rcon_query(cmd)
            if resp is not None:
                return str(resp).strip()
        except Exception as e:
            logger.warning(f"PAPI RCON 查询失败，使用本地替换: {e}")

    return _local_replace(player, text)


def run_placeholder_blocking(player: str, text: str, use_rcon: bool = True, timeout: float = 5.0) -> str:
    """
    同步环境下的便捷调用：有事件循环则用 run_coroutine_threadsafe，否则新建 loop。
    """
    try:
        loop = asyncio.get_running_loop()
        fut = asyncio.run_coroutine_threadsafe(run_placeholder(player, text, use_rcon), loop)
        return fut.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(run_placeholder(player, text, use_rcon))
    except Exception:
        return _local_replace(player, text)


@EasyBotWsClient.listen_exec_op("PLACEHOLDER_API_QUERY")
async def on_placeholder_api_query(ctx: ExecContext, data: dict, _):
    query_text = data.get("query_text", "")
    player = data.get("player_name", "")

    if not _is_bukkit_server():
        await ctx.callback({
            "success": False,
            "text": f"PAPI 不可用 (非 Bukkit 服务端): {query_text}"
        })
        return

    # Bukkit: 尝试通过 RCON 查询
    server = ServerInterface.get_instance()
    if server.is_rcon_running():
        try:
            resp = server.rcon_query(f'papi parse {player} "{query_text}"')
            if resp is not None:
                await ctx.callback({
                    "success": True,
                    "text": str(resp).strip()
                })
                return
        except Exception as e:
            server.logger.warning(f"PAPI RCON 查询失败: {e}")

    await ctx.callback({
        "success": False,
        "text": f"PAPI 查询失败: {query_text}"
    })
