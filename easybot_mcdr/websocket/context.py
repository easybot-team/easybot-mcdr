import json


class ExecContext:
    def __init__(self, callback_id: str, exec_op: str, wsc):
        self.callback_id = callback_id
        self.exec_op = exec_op
        self.ws = wsc

    async def callback(self, data: dict):
        packet = {
            "op": 5,
            "callback_id": self.callback_id,
            "exec_op": self.exec_op
        }
        packet.update(data)
        await self.ws.send(json.dumps(packet))