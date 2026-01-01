from typing import List, Protocol

from easybot_mcdr.message import Segment


class BridgeBehavior(Protocol):
    """
    行为适配层，用于抽象“主程序”需要的能力，便于按需替换/扩展。
    """

    def run_command(self, player_name: str, command: str, enable_papi: bool) -> str:
        ...

    def papi_query(self, player_name: str, query: str) -> str:
        ...

    def get_info(self):
        """返回服务器信息对象（可自定义结构）。"""
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
