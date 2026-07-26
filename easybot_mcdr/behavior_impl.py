"""
MCDR 端 behavior 基础设施。

历史遗留：本模块曾包含 run_command/papi_query/sync_to_chat 等函数，
但它们与 impl/bridge_behavior_impl.py 的 DefaultBridgeBehavior 功能重复，
且实际调用方都使用 DefaultBridgeBehavior，本模块的这些函数无人引用。

现在只保留 PlayerDataGetter 的初始化和获取，供 NBT 读取使用。
"""
import logging

logger = logging.getLogger("EasyBot")

_server = None
_player_data_getter = None


def set_server(server):
    """初始化 PlayerDataGetter，需在插件 on_load 时调用。"""
    global _server, _player_data_getter
    _server = server
    if server is not None:
        from .api.player_data import PlayerDataGetter
        _player_data_getter = PlayerDataGetter(server)


def get_player_data_getter():
    """获取 PlayerDataGetter 实例，供 NBT 数据读取使用。"""
    return _player_data_getter
