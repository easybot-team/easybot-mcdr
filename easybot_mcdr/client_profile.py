class ClientProfile:
    """
    静态能力检测状态，参照 Java bridge 的 ClientProfile。
    在 GET_SERVER_INFO RPC 处理时更新这些状态。
    """
    is_command_supported: bool = True
    is_papi_supported: bool = False
    is_online_mode: bool = False
    is_debug_mode: bool = False
    has_geyser: bool = False
    has_floodgate: bool = False
    has_skins_restorer: bool = False
    sync_message_mode: int = 0
    sync_message_money: int = 0

    plugin_version: str = "unknown"
    server_description: str = ""

    @classmethod
    def update(cls, **kwargs):
        for k, v in kwargs.items():
            if hasattr(cls, k):
                setattr(cls, k, v)

    @classmethod
    def to_dict(cls) -> dict:
        return {
            "is_command_supported": cls.is_command_supported,
            "is_papi_supported": cls.is_papi_supported,
            "is_online_mode": cls.is_online_mode,
            "is_debug_mode": cls.is_debug_mode,
            "has_geyser": cls.has_geyser,
            "has_floodgate": cls.has_floodgate,
            "has_skins_restorer": cls.has_skins_restorer,
            "sync_message_mode": cls.sync_message_mode,
            "sync_message_money": cls.sync_message_money,
        }
