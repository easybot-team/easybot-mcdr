import pytest
import asyncio
import json
import websockets
from unittest.mock import patch, MagicMock


class SimpleWsClient:
    """简化的 WebSocket 客户端，用于测试"""

    def __init__(self, url):
        self.ws_url = url
        self._ws = None
        self._active = False
        self.messages_received = []

    async def connect(self):
        self._active = True
        self._ws = await websockets.connect(self.ws_url)

    async def send(self, message):
        if self._ws:
            await self._ws.send(message)

    async def recv(self):
        if self._ws:
            return await self._ws.recv()

    async def close(self):
        self._active = False
        if self._ws:
            await self._ws.close()


@pytest.mark.asyncio
async def test_mock_server_starts(mock_server):
    """测试 mock 服务器能正常启动"""
    assert mock_server.get_port() > 0


@pytest.mark.asyncio
async def test_websocket_connection(ws_url, mock_server):
    """测试 WebSocket 连接"""
    client = SimpleWsClient(ws_url)
    await client.connect()

    # 验证连接
    assert client._ws is not None
    assert client._ws.state is websockets.State.OPEN

    await client.close()


@pytest.mark.asyncio
async def test_session_info_received(ws_url, mock_server):
    """测试收到会话信息"""
    client = SimpleWsClient(ws_url)
    await client.connect()

    # 接收会话信息
    msg = await client.recv()
    data = json.loads(msg)

    assert data["op"] == 0
    assert data["version"] == "MockBridgeCore"
    assert "session_id" in data

    await client.close()


@pytest.mark.asyncio
async def test_auth_success(ws_url, mock_server):
    """测试鉴权成功"""
    client = SimpleWsClient(ws_url)
    await client.connect()

    # 接收会话信息
    await client.recv()

    # 发送鉴权
    auth_packet = {
        "op": 1,
        "token": "test_token_12345",
        "plugin_version": "test",
        "server_description": "MCDR_Test"
    }
    await client.send(json.dumps(auth_packet))

    # 接收鉴权响应
    msg = await client.recv()
    data = json.loads(msg)

    assert data["op"] == 3
    assert data["server_name"] == "test_server"

    await client.close()


@pytest.mark.asyncio
async def test_auth_failed(ws_url, mock_server):
    """测试鉴权失败"""
    client = SimpleWsClient(ws_url)
    await client.connect()

    # 接收会话信息
    await client.recv()

    # 发送错误的 token
    auth_packet = {
        "op": 1,
        "token": "wrong_token",
        "plugin_version": "test",
        "server_description": "MCDR_Test"
    }
    await client.send(json.dumps(auth_packet))

    # 接收鉴权响应
    msg = await client.recv()
    data = json.loads(msg)

    assert data["op"] == 3
    assert data["server_name"] == "auth_failed"

    await client.close()


@pytest.mark.asyncio
async def test_message_received_by_server(ws_url, mock_server):
    """测试服务端收到消息"""
    client = SimpleWsClient(ws_url)
    await client.connect()

    # 接收会话信息
    await client.recv()

    # 发送心跳
    await client.send(json.dumps({"op": 2}))

    # 等待消息处理
    await asyncio.sleep(0.1)

    # 验证服务端收到消息
    assert not mock_server.messages.empty()
    received = mock_server.messages.get_nowait()
    assert received["op"] == 2

    await client.close()
