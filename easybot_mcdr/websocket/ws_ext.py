import asyncio
import json
from easybot_mcdr.event_bus import EventBus
from easybot_mcdr.websocket.ws import EasyBotWsClient


class ExtendedEasyBotWsClient(EasyBotWsClient):
    """
    扩展版本：增加事件总线、回调超时事件，并在消息流程中提供更细粒度事件。
    """

    event_bus = EventBus()

    async def send_and_wait(self, exec_op: str, data: dict, timeout: float = 10.0):
        """
        复制基类逻辑以保留 callback_id，增加超时事件。
        """
        callback_id = f"req_{self._request_counter}"
        self._request_counter += 1

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[callback_id] = future

        try:
            packet = {
                "op": 4,
                "exec_op": exec_op,
                "callback_id": str(callback_id)
            }
            packet.update(data)

            await self.send(json.dumps(packet))

            try:
                return await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError as e:
                await self.event_bus.emit(
                    "request_timeout",
                    exec_op=exec_op,
                    callback_id=callback_id,
                    data=data,
                    timeout=timeout,
                )
                raise e
        finally:
            self._pending_requests.pop(callback_id, None)

    async def on_open(self):
        await super().on_open()
        await self.event_bus.emit("connected")

    async def on_close(self, code, reason):
        await super().on_close(code, reason)
        await self.event_bus.emit("disconnected", code=code, reason=reason)

    async def on_error(self, error):
        await super().on_error(error)
        await self.event_bus.emit("error", error=error)

    async def on_message(self, message):
        # 先解析方便事件分发，再调用基类处理
        try:
            data = json.loads(message)
            op = data.get("op")
        except Exception:
            data = None
            op = None

        await super().on_message(message)

        # 事件分发
        await self.event_bus.emit("raw_packet", message=message, data=data)
        if op == 3:
            # 身份验证成功
            await self.event_bus.emit("identified", session_info=self._session_info, data=data)
