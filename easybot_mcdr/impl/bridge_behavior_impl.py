from typing import List

from mcdreforged.api.all import PluginServerInterface
from easybot_mcdr.bridge_behavior import BridgeBehavior
from easybot_mcdr.message import Segment, segments_to_list


class DefaultBridgeBehavior(BridgeBehavior):
    def __init__(self, server: PluginServerInterface):
        self.server = server

    def run_command(self, player_name: str, command: str, enable_papi: bool) -> str:
        # PAPI 支持已移除，直接执行原命令
        cmd = command

        try:
            if self.server.is_rcon_running():
                return str(self.server.rcon_query(cmd))
            else:
                # fallback：直接执行命令
                self.server.execute(cmd)
                return "executed"
        except Exception as e:
            return f"error: {e}"

    def papi_query(self, player_name: str, query: str) -> str:
        # 已移除 PAPI 支持，原样返回
        return query

    def get_info(self):
        info = self.server.get_server_information()
        return {
            "name": getattr(info, "server_name", getattr(info, "server_brand", "unknown")),
            "version": getattr(info, "version", "unknown"),
            "max_players": getattr(info, "max_players", getattr(info, "max_player", None)),
            "description": getattr(info, "description", ""),
            "port": getattr(info, "port", None),
        }

    def sync_to_chat(self, message: str):
        self.server.say(message)

    def bind_success_broadcast(self, player_name: str, account_id: str, account_name: str):
        self.server.say(f"[EasyBot] 玩家 {player_name} 绑定账号 {account_name} ({account_id}) 成功")

    def kick_player(self, player: str, kick_message: str):
        try:
            self.server.execute(f"kick {player} {kick_message}")
        except Exception:
            # fallback to RCON if available
            if self.server.is_rcon_running():
                self.server.rcon_query(f"kick {player} {kick_message}")

    def sync_to_chat_extra(self, segments: List[Segment], text: str):
        # 简化：仅用文本部分输出，其余 segment 转换为字符串描述
        try:
            if segments:
                pretty = " ".join([s.to_dict().__str__() for s in segments])
                self.server.say(f"{text} {pretty}")
            else:
                self.server.say(text)
        except Exception:
            self.server.say(text)

    def get_player_list(self):
        return list(self.server.get_online_players())
