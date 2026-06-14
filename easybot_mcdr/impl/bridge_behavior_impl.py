from typing import List, Optional

from mcdreforged.api.all import PluginServerInterface
from easybot_mcdr.bridge_behavior import BridgeBehavior
from easybot_mcdr.message import Segment


class DefaultBridgeBehavior(BridgeBehavior):
    def __init__(self, server: PluginServerInterface):
        self.server = server

    def run_command(self, player_name: str, command: str, enable_papi: bool) -> str:
        cmd = command
        try:
            # MCDR 命令 (!! 开头) 不经过 RCON, 直接通过 server.execute() 执行
            if cmd.strip().startswith("!!"):
                self.server.execute(cmd)
                return "(MCDR 命令已执行)"
            # 服务端命令优先使用 RCON 获取输出
            if self.server.is_rcon_running():
                return str(self.server.rcon_query(cmd))
            else:
                self.server.execute(cmd)
                return "(命令已执行, RCON 未启用无法获取输出)"
        except Exception as e:
            return f"error: {e}"

    def papi_query(self, player_name: str, query: str) -> str:
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
            if self.server.is_rcon_running():
                self.server.rcon_query(f"kick {player} {kick_message}")

    def sync_to_chat_extra(self, segments: List[Segment], text: str):
        try:
            if segments:
                from easybot_mcdr.impl.message_sync import render_segments
                render_segments(segments, text)
            else:
                self.server.say(text)
        except Exception:
            self.server.say(text)

    def get_player_list(self):
        return list(self.server.get_online_players())

    def module_is_installed(self, name: str) -> bool:
        return False

    def module_is_enabled(self, name: str) -> bool:
        return False

    def is_authenticated(self, name: str) -> bool:
        return False

    def get_player_skin(self, player_name: str) -> Optional[dict]:
        from easybot_mcdr.impl.get_server_info import get_online_mode, get_skins_restorer
        online = get_online_mode()
        has_sr = get_skins_restorer()

        skin_url = None
        cape_url = None

        if online or has_sr:
            skin_url = f"https://mineskin.eu/download/{player_name}"
        else:
            # 离线模式无皮肤站: 查询 Mojang 判断是否正版
            from easybot_mcdr.impl.player_list import _check_premium_sync
            if _check_premium_sync(player_name):
                skin_url = f"https://mineskin.eu/download/{player_name}"
            else:
                # 非正版: 尝试通过 UUID 获取头像
                try:
                    players = self.server.get_online_players()
                    for p in players:
                        if hasattr(p, 'name') and p.name == player_name:
                            skin_url = f"https://mc-heads.net/skin/{p.uuid}"
                            break
                        if str(p) == player_name:
                            skin_url = f"https://mc-heads.net/skin/{p.uuid}"
                            break
                except Exception:
                    pass

        if skin_url:
            return {"skin_url": skin_url, "cape_url": cape_url}
        return None

    def read_nbt_data(self, player_uuid: str, data_type: int) -> Optional[dict]:
        """
        读取玩家 NBT 数据
        data_type: 0=PlayerData, 1=Advancements, 2=Statistics
        """
        from easybot_mcdr.behavior_impl import get_player_data_getter
        getter = get_player_data_getter()
        if getter is None:
            return None
        return getter.read_nbt_data(player_uuid, data_type)
