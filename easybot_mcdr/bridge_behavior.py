from typing import List, Optional, Protocol

from easybot_mcdr.message import Segment


class BridgeBehavior(Protocol):
    def run_command(self, player_name: str, command: str, enable_papi: bool) -> str:
        ...

    def papi_query(self, player_name: str, query: str) -> str:
        ...

    def get_info(self):
        ...

    def sync_to_chat(self, message: str) -> None:
        ...

    def bind_success_broadcast(self, player_name: str, account_id: str, account_name: str) -> None:
        ...

    def kick_player(self, player: str, kick_message: str) -> None:
        ...

    def sync_to_chat_extra(self, segments: List[Segment], text: str) -> None:
        ...

    def get_player_list(self):
        ...

    def module_is_installed(self, name: str) -> bool:
        ...

    def module_is_enabled(self, name: str) -> bool:
        ...

    def is_authenticated(self, name: str) -> bool:
        ...

    def get_player_skin(self, player_name: str) -> Optional[dict]:
        ...

    def read_nbt_data(self, player_uuid: str, data_type: int) -> Optional[dict]:
        ...
