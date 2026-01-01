import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional


# 注册 RPC 处理器的简单装饰器，基于 exec_op 与 EasyBotWsClient 的 listen_exec_op 机制
_registry: Dict[str, Callable[..., Awaitable[Any]]] = {}


def bridge_rpc(exec_op: str, description: str = "") -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    注册一个 RPC 处理器，对应 exec_op。
    装饰后的函数签名: (ctx: ExecContext, data: dict, session_info) -> Any/awaitable
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        _registry[exec_op] = func

        # 延迟导入以避免循环依赖
        try:
            from easybot_mcdr.websocket.ws import EasyBotWsClient
            EasyBotWsClient.listen_exec_op(exec_op)(func)
        except Exception:
            # 如果还未加载 EasyBotWsClient，可以在运行时手动 bind_registered_handlers
            pass

        return func

    return decorator


def bind_registered_handlers():
    """
    当 EasyBotWsClient 已加载但 decorator 注册时未找到类，可调用此函数补注册。
    """
    from easybot_mcdr.websocket.ws import EasyBotWsClient

    for exec_op, handler in _registry.items():
        EasyBotWsClient.listen_exec_op(exec_op)(handler)
