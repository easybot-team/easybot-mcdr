import asyncio
from collections import defaultdict
import json
import time
import uuid
from types import SimpleNamespace
import websockets
from typing import Optional, Dict, Any, Callable, List
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from mcdreforged.api.all import *
from easybot_mcdr.config import get_config
from easybot_mcdr.meta import get_plugin_version
from easybot_mcdr.websocket.context import ExecContext


class SessionInfo:
    def __init__(self, version: str, system: str, dotnet: str, session_id: str, token: str, interval: int):
        self.version = version
        self.system = system
        self.dotnet = dotnet
        self.session_id = session_id
        self.token = token
        self.interval = interval
        self.server_name = None

    @staticmethod
    def from_dict(data: dict):
        return SessionInfo(
            version=data["version"],
            system=data["system"],
            dotnet=data["dotnet"],
            session_id=data["session_id"],
            token=data["token"],
            interval=data["interval"]
        )

    def get_version(self):
        return self.version

    def get_system(self):
        return self.system

    def get_dotnet(self):
        return self.dotnet

    def get_session_id(self):
        return self.session_id

    def get_token(self):
        return self.token

    def get_interval(self):
        return self.interval

    def set_server_name(self, server_name: str):
        self.server_name = server_name

    def get_server_name(self):
        return self.server_name


class EasyBotWsClient:
    _listeners = defaultdict(list)

    @classmethod
    def listen_exec_op(cls, exec_op: str):
        def decorator(func):
            cls._listeners[exec_op].append(func)
            return func
        return decorator

    def __init__(self, url, mcdr_server=None):
        self.ws_url = str(url) if url is not None else ""
        self.mcdr_server = mcdr_server
        self._conn_lock = asyncio.Lock()
        self._is_connecting = False
        self._ws = None
        self._active = False
        self._manual_stop = False
        self._reconnect_delay = 5
        self._max_reconnect_attempts = 30
        self._reconnect_attempts = 0
        self._session_info = None
        self._heartbeat_task = None
        self._connection_task = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_counter = 0

    async def is_connected(self):
        return (self._ws is not None
                and hasattr(self._ws, 'state')
                and self._ws.state is websockets.State.OPEN)

    async def send_and_wait(self, exec_op: str, data: dict, timeout: float = 10.0) -> dict:
        callback_id = f"req_{uuid.uuid4().hex[:12]}"
        self._request_counter += 1

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[callback_id] = future

        try:
            packet = {
                "op": 4,
                "exec_op": exec_op,
                "callback_id": callback_id
            }
            packet.update(data)
            await self.send(json.dumps(packet))
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending_requests.pop(callback_id, None)

    async def start(self):
        async with self._conn_lock:
            if self._active or self._is_connecting:
                return
            self._active = True
            self._manual_stop = False
            self._is_connecting = True
            self._connection_task = asyncio.create_task(self._connection_manager())

    async def stop(self):
        self._active = False
        self._manual_stop = True

        if self._ws and self._ws.state is websockets.State.OPEN:
            await self._ws.close(reason="MCDR插件端主动关闭连接")
        self._ws = None

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
            self._connection_task = None

        self._is_connecting = False
        try:
            ServerInterface.get_instance().logger.info("WebSocket 客户端已停止")
        except Exception:
            pass

    async def _start_heartbeat(self, interval_seconds: int):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        async def heartbeat_loop():
            try:
                while True:
                    await asyncio.sleep(max(10, interval_seconds - 10))
                    if not (self._active and self._ws and self._ws.state is websockets.State.OPEN):
                        break
                    await self.send(json.dumps({"op": 2}))
            except (ConnectionClosed, asyncio.CancelledError):
                pass

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def _connection_manager(self):
        try:
            while self._active:
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    try:
                        ServerInterface.get_instance().logger.warning(
                            f"[EasyBot] 已达到最大重连次数({self._max_reconnect_attempts}次)，停止重连")
                    except Exception:
                        pass
                    self._active = False
                    break

                if self._reconnect_attempts > 0:
                    try:
                        ServerInterface.get_instance().logger.info(
                            f"[EasyBot] {self._reconnect_delay}秒后尝试重连 "
                            f"(第{self._reconnect_attempts}次/共{self._max_reconnect_attempts}次)")
                    except Exception:
                        pass
                    await asyncio.sleep(self._reconnect_delay)

                try:
                    async with websockets.connect(self.ws_url) as websocket:
                        self._ws = websocket
                        self._reconnect_attempts = 0
                        await self.on_open()
                        await self._message_pump()
                except (ConnectionRefusedError, ConnectionClosedError):
                    self._reconnect_attempts += 1
                    try:
                        ServerInterface.get_instance().logger.warning(
                            f"[EasyBot] 连接失败 (第{self._reconnect_attempts}次/共{self._max_reconnect_attempts}次)")
                    except Exception:
                        pass
                except Exception as e:
                    self._reconnect_attempts += 1
                    try:
                        ServerInterface.get_instance().logger.warning(
                            f"[EasyBot] 连接异常: {type(e).__name__}")
                    except Exception:
                        pass
        finally:
            self._is_connecting = False
            await self._cleanup_connection()

    async def _message_pump(self):
        try:
            while self._active and self._ws.state is websockets.State.OPEN:
                try:
                    message = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
                    await self.on_message(message)
                except asyncio.TimeoutError:
                    continue
        except ConnectionClosed as e:
            await self.on_close(e.code, e.reason)

    async def _cleanup_connection(self):
        if self._ws and self._ws.state is websockets.State.OPEN:
            await self._ws.close(reason="MCDR端清理连接资源主动关闭")
        self._ws = None

    async def send(self, message):
        if not (self._active and self._ws and self._ws.state is websockets.State.OPEN):
            raise ConnectionError("当前WebSocket客户端不在线,插件可能还未连接到EasyBot服务!")

        if get_config()["debug"]:
            try:
                ServerInterface.get_instance().logger.info(f"[EasyBot] 发送: {message}")
            except Exception:
                pass

        await self._ws.send(message)

    async def on_open(self):
        try:
            ServerInterface.get_instance().logger.info("[EasyBot] 已与主程序建立连接")
        except Exception:
            pass

    async def on_message(self, message):
        try:
            server = ServerInterface.get_instance()
            if get_config()["debug"]:
                server.logger.info(f"[EasyBot] 收到: {message}")
            data = json.loads(message)
            op = data["op"]
            if op == 0:
                self._session_info = SessionInfo.from_dict(data)
                info = self._session_info
                server.logger.info(
                    f"[EasyBot] 目标核心版本: {info.get_version()}-{info.get_system()} "
                    f"[{info.get_dotnet()}] 心跳{info.get_interval()}s "
                    f"会话ID: {info.get_session_id()}")
                server.logger.info("[EasyBot] 准备发送鉴权")
                await self.send(json.dumps({
                    "op": 1,
                    "token": get_config()["token"],
                    "plugin_version": get_plugin_version(),
                    "server_description": f"MCDR_{server.get_server_information().version}",
                }))
            elif op == 3:
                self._session_info.set_server_name(data["server_name"])
                server.logger.info(f"[EasyBot] 身份验证成功... [{data['server_name']}]")
                await self.start_update_sync_settings()
                if self._session_info is not None:
                    interval = self._session_info.get_interval()
                    await self._start_heartbeat(interval)
            elif op == 4:
                exec_op = data.get("exec_op")
                if exec_op in self._listeners:
                    ctx = ExecContext(data["callback_id"], data["exec_op"], self)
                    for handler in self._listeners[exec_op]:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(ctx, data, self._session_info)
                            else:
                                handler(ctx, data, self._session_info)
                        except Exception as e:
                            server.logger.error(f"[EasyBot] 处理 exec_op={exec_op} 时出错: {str(e)}")
                else:
                    callback_id = data.get("callback_id")
                    if callback_id:
                        try:
                            await self.send(json.dumps({
                                "op": 5,
                                "callback_id": callback_id,
                                "exec_op": exec_op,
                                "success": False,
                                "text": f"unknown exec_op: {exec_op}"
                            }))
                        except Exception:
                            pass
            elif op == 5:
                callback_id = data.get("callback_id")
                if callback_id in self._pending_requests:
                    future = self._pending_requests.pop(callback_id)
                    if not future.done():
                        future.set_result(data)
        except Exception as e:
            try:
                ServerInterface.get_instance().logger.error(f"[EasyBot] 处理消息时出错: {str(e)}")
            except Exception:
                pass

    async def on_close(self, code, reason):
        try:
            ServerInterface.get_instance().logger.info(f"[EasyBot] 连接关闭: {code} {reason}")
        except Exception:
            pass

    async def on_error(self, error):
        try:
            ServerInterface.get_instance().logger.warning(f"[EasyBot] WebSocket错误: {error}")
        except Exception:
            pass

    async def _send_packet(self, exec_op: str, data: dict):
        if self._active:
            packet = {
                "op": 4,
                "exec_op": exec_op,
                "callback_id": "0"
            }
            packet.update(data)
            await self.send(json.dumps(packet))

    async def login(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        data = await self.send_and_wait("PLAYER_JOIN", {
            "player": build_player_info(player_name)
        }, 5)
        return data

    async def report_player(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        if info is None:
            try:
                ServerInterface.get_instance().logger.warning(
                    f"[EasyBot] 无法获取 {player_name} 的玩家信息，跳过报告")
            except Exception:
                pass
            return None
        # 发送完整的玩家信息，包括所有必要字段
        await self._send_packet("REPORT_PLAYER", {
            "player_name": player_name,
            "player_uuid": info["player_uuid"],
            "player_ip": info["ip"],
            "skin_url": info.get("skin_url", ""),
            "bedrock": info.get("bedrock", False),
        })
        return info

    async def push_message(self, player_name: str, message: str, use_command: bool, extra: list = None):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        if info is None:
            try:
                ServerInterface.get_instance().logger.warning(
                    f"无法获取 {player_name} 的玩家信息，跳过消息上报")
            except Exception:
                pass
            return
        info['player_name_raw'] = player_name
        packet = {
            "player": info,
            "message": message,
            "use_command": use_command
        }
        if extra:
            packet["extra"] = extra
        await self._send_packet("SYNC_MESSAGE", packet)

    async def push_death(self, player_name: str, killer: str, message: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name
        await self._send_packet("SYNC_DEATH_MESSAGE", {
            "player": info,
            "raw": message,
            "killer": killer
        })

    async def push_enter(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name
        await self._send_packet("SYNC_ENTER_EXIT_MESSAGE", {
            "player": info,
            "is_enter": True
        })

    async def push_exit(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name
        await self._send_packet("SYNC_ENTER_EXIT_MESSAGE", {
            "player": info,
            "is_enter": False
        })

    async def get_social_account(self, player_name: str):
        return await self.send_and_wait("GET_SOCIAL_ACCOUNT", {
            "player_name": player_name
        })

    async def start_bind(self, player_name: str):
        return await self.send_and_wait("START_BIND", {
            "player_name": player_name
        })

    async def push_cross_server_message(self, player: str, message: str):
        config = get_config()
        server_name = config["server_name"]
        await self._send_packet("CROSS_SERVER_SAY", {
            "server_name": server_name,
            "player": player,
            "message": message
        })

    async def start_update_sync_settings(self):
        await self._send_packet("NEED_SYNC_SETTING", {})

    async def server_state(self, players_str: str):
        await self._send_packet("SERVER_STATE_CHANGED", {
            "token": get_config()["token"],
            "players": players_str
        })

    async def data_record(self, record_type: str, data: str, name: str):
        await self._send_packet("DATA_RECORD", {
            "type": record_type,
            "data": data,
            "name": name,
            "token": get_config()["token"]
        })

    async def get_new_version(self):
        return await self.send_and_wait("GET_NEW_VERSION", {})

    async def get_bind_info(self, player_name: str):
        return await self.send_and_wait("GET_BIND_INFO", {
            "player_name": player_name
        })
