import asyncio
import re
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *


def get_placeholders(text: str) -> list[str]:
    return re.findall(r"%\w+%", text)


def _local_replace(player: str, text: str) -> str:
    server = ServerInterface.get_instance()
    logger = server.logger
    query_text = text
    for placeholder in get_placeholders(query_text):
        if placeholder.lower() == "%player_name%":
            query_text = query_text.replace(placeholder, player)
        else:
            logger.warning(f"不支持的变量: {placeholder} [注意, 仅提供基础变量替换]")
    return query_text


async def run_placeholder(player: str, text: str, use_rcon: bool = True) -> str:
    """
    优先通过 RCON 调用 PAPI (papi parse <player> "<text>")，失败则回退本地基础替换。
    适用于 Fabric 后端：需后端安装 PlaceholderAPI 并允许控制台执行 papi 命令。
    """
    server = ServerInterface.get_instance()
    logger = server.logger

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
    await ctx.callback({
        "success": False,
        "text": f"PAPI unavailable: {query_text}"
    })