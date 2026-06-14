import pytest
import asyncio
import json
import websockets
from queue import Queue
from contextlib import asynccontextmanager


class MockEasyBotServer:
    """模拟 EasyBot WebSocket 服务端"""

    def __init__(self, host="localhost", port=0):
        self.host = host
        self.port = port
        self.server = None
        self.clients = []
        self.messages = Queue()
        self.token = "test_token_12345"
        self.server_name = "test_server"

    async def handler(self, websocket):
        self.clients.append(websocket)
        try:
            # 发送会话信息
            session_info = {
                "op": 0,
                "version": "MockBridgeCore",
                "system": "Test",
                "dotnet": "test",
                "session_id": "test-session-id",
                "token": self.token,
                "interval": 30
            }
            await websocket.send(json.dumps(session_info))

            # 处理消息
            async for message in websocket:
                data = json.loads(message)
                self.messages.put(data)

                # 处理鉴权
                if data.get("op") == 1:
                    if data.get("token") == self.token:
                        await websocket.send(json.dumps({
                            "op": 3,
                            "server_name": self.server_name
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "op": 3,
                            "server_name": "auth_failed"
                        }))
        finally:
            self.clients.remove(websocket)

    async def start(self):
        self.server = await websockets.serve(self.handler, self.host, self.port)
        actual_port = self.server.sockets[1].getsockname()[1]
        self.port = actual_port
        return actual_port

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    def get_port(self):
        return self.port


@pytest.fixture
async def mock_server():
    """提供 mock 服务器"""
    server = MockEasyBotServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def ws_url(mock_server):
    """提供 WebSocket URL"""
    return f"ws://localhost:{mock_server.get_port()}"
