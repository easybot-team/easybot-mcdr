import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple


Handler = Callable[..., Any]


@dataclass(order=True)
class _QueuedHandler:
    priority: int
    handler: Handler = field(compare=False)


class EventBus:
    """
    轻量事件总线，支持优先级与同步/异步处理器。
    用于在 MCDR 插件内部模拟 Java 侧的 BridgeEventManager。
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[_QueuedHandler]] = {}

    def on(self, event: str, priority: int = 0) -> Callable[[Handler], Handler]:
        """
        装饰器方式注册事件处理器。
        事件名建议小写，示例: "connected" / "disconnected" / "raw_packet".
        """

        def decorator(func: Handler) -> Handler:
            self.register(event, func, priority)
            return func

        return decorator

    def register(self, event: str, handler: Handler, priority: int = 0) -> None:
        queue = self._handlers.setdefault(event, [])
        queue.append(_QueuedHandler(priority, handler))
        queue.sort(reverse=True)  # 高优先级先执行

    async def emit(self, event: str, **kwargs: Any) -> None:
        """
        触发事件；按优先级顺序执行，同步函数直接调用，协程函数 await。
        """
        queue = list(self._handlers.get(event, []))
        for item in queue:
            try:
                if asyncio.iscoroutinefunction(item.handler):
                    await item.handler(**kwargs)
                else:
                    item.handler(**kwargs)
            except Exception as e:
                # 不中断后续处理，记录到 MCDR 日志（若可用）
                try:
                    from mcdreforged.api.all import ServerInterface

                    ServerInterface.get_instance().logger.warning(
                        f"[EasyBot] Event '{event}' handler error: {type(e).__name__}: {e}"
                    )
                except Exception:
                    pass
