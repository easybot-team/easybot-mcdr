import logging
from typing import List, Optional

from mcdreforged.command.command_source import CommandSource

logger = logging.getLogger("EasyBot")

_server = None
_player_data_getter = None


def set_server(server):
    global _server, _player_data_getter
    _server = server
    if server is not None:
        from .api.player_data import PlayerDataGetter
        _player_data_getter = PlayerDataGetter(server)


def get_server():
    return _server


def get_player_data_getter():
    return _player_data_getter


class _OutputCaptureSource(CommandSource):
    def __init__(self, server):
        super().__init__(server)
        self._output = []

    def reply(self, text):
        self._output.append(str(text))

    def get_output(self) -> str:
        return "\n".join(self._output) if self._output else ""


def is_mcdr_command(command: str) -> bool:
    return command.strip().startswith("!!")


def run_command(player_name: str, command: str, enable_papi: bool) -> str:
    if _server is None:
        return ""

    if is_mcdr_command(command):
        return _run_mcdr_command(command)

    try:
        result = _server.rcon_query(command)
        if result is not None:
            return result
    except Exception:
        pass

    _server.execute(command)
    return ""


def _run_mcdr_command(command: str) -> str:
    try:
        source = _OutputCaptureSource(_server)
        _server.execute_command(command, source)
        output = source.get_output()
        return output if output else f"[MCDR] 命令已执行: {command}"
    except Exception as e:
        return f"[MCDR] 命令执行失败: {e}"


def papi_query(player_name: str, query: str) -> str:
    return query


def get_info() -> dict:
    if _server is None:
        return {}
    info = _server.get_server_information()
    return {
        "server_name": _server.get_server_name(),
        "server_version": info.version,
        "plugin_version": "1.7.5",
        "is_papi_supported": False,
        "is_command_supported": True,
        "has_geyser": False,
        "is_online_mode": info.is_online_mode,
    }


def sync_to_chat(message: str):
    if _server is None:
        return
    _server.tell(color=None, msg=message)


def sync_to_chat_extra(segments: List, text: str):
    parts = []
    for seg in segments:
        t = seg.get_text() if hasattr(seg, "get_text") else str(seg)
        if t:
            parts.append(t)
    combined = "".join(parts) if parts else text
    sync_to_chat(combined)


def bind_success_broadcast(player_name: str, account_id: str, account_name: str):
    sync_to_chat(f"[EasyBot] {player_name} 绑定成功! 账号: {account_name}")


def kick_player(player: str, kick_message: str):
    if _server is None:
        return
    _server.execute(f"kick {player} {kick_message}")


def module_is_installed(module_name: str) -> bool:
    if _server is None:
        return False
    try:
        plugin_list = _server.get_plugin_list()
        return any(module_name.lower() in p.lower() for p in plugin_list)
    except Exception:
        return False


def module_is_enabled(module_name: str) -> bool:
    return module_is_installed(module_name)


def get_player_list() -> List[dict]:
    if _server is None:
        return []
    players = _server.get_online_player_list()
    return [{"player_name": p} for p in players]


def get_player_skin(player_name: str) -> Optional[dict]:
    return None


def read_nbt_data(player_uuid: str, data_type: int) -> Optional[dict]:
    if _player_data_getter is None:
        return None
    return _player_data_getter.read_nbt_data(player_uuid, data_type)


def get_entity_data(player: str, path: str = "", timeout: float = 5.0) -> Optional[dict]:
    if _player_data_getter is None:
        return None
    return _player_data_getter.get_entity_data(player, path, timeout)
