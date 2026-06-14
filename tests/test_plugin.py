"""
EasyBot-MCDR 插件测试套件
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── 1. 模块导入测试 ─────────────────────────────────────────────────
def test_import_config():
    from easybot_mcdr.config import get_config, load_config, save_config
    assert callable(get_config)


def test_import_meta():
    from easybot_mcdr.meta import get_plugin_version
    assert callable(get_plugin_version)


def test_import_message():
    from easybot_mcdr.message import (
        Segment, SegmentType, TextSegment, ImageSegment,
        FileSegment, AtSegment, ReplySegment, UnknownSegment,
        segments_from_list, segments_to_list,
    )


def test_import_rpc():
    from easybot_mcdr.rpc import bridge_rpc, bind_registered_handlers, _registry
    assert callable(bridge_rpc)
    assert isinstance(_registry, dict)


def test_import_event_bus():
    from easybot_mcdr.event_bus import EventBus
    eb = EventBus()
    assert hasattr(eb, "on")
    assert hasattr(eb, "emit")


def test_import_prefix_handler():
    from easybot_mcdr.impl.prefix_handler import PrefixNameHandler
    assert callable(PrefixNameHandler)


def test_import_ws_client():
    from easybot_mcdr.websocket.ws import EasyBotWsClient, SessionInfo
    assert hasattr(EasyBotWsClient, "listen_exec_op")
    assert hasattr(SessionInfo, "from_dict")


def test_import_player_api():
    from easybot_mcdr.api.player import (
        PlayerInfo, generate_offline_uuid, update_player_uuid,
        get_data_map, check_cache, check_online, get_player_list,
    )
    assert callable(generate_offline_uuid)


def test_import_impl_modules():
    """验证所有 impl 子模块均可导入。"""
    import easybot_mcdr.impl.rpc_handlers
    import easybot_mcdr.impl.un_bind_notify
    import easybot_mcdr.impl.message_sync
    import easybot_mcdr.impl.exec_command
    import easybot_mcdr.impl.cross_server_chat
    import easybot_mcdr.impl.player_list
    import easybot_mcdr.impl.papi
    import easybot_mcdr.impl.get_server_info
    import easybot_mcdr.impl.bridge_behavior_impl


# ── 2. 配置加载测试 ─────────────────────────────────────────────────
def test_config_json_parse():
    config_path = PROJECT_ROOT / "data" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert isinstance(cfg, dict)
    assert "token" in cfg
    assert "ws" in cfg


def test_config_required_fields():
    config_path = PROJECT_ROOT / "data" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["token", "ws", "server_name", "debug", "kick_delay_seconds",
                 "message_sync", "message", "enable_white_list", "events",
                 "bot_filter"]
    for key in required:
        assert key in cfg, f"缺少必填配置项: {key}"


def test_config_bot_filter():
    config_path = PROJECT_ROOT / "data" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    bf = cfg["bot_filter"]
    assert "enabled" in bf
    assert "prefixes" in bf
    assert isinstance(bf["prefixes"], list)
    assert len(bf["prefixes"]) > 0


# ── 3. 消息模型测试 ─────────────────────────────────────────────────
def test_text_segment():
    from easybot_mcdr.message import TextSegment, SegmentType, Segment
    seg = TextSegment("hello")
    assert seg.type == SegmentType.TEXT
    assert seg.text == "hello"
    d = seg.to_dict()
    assert d == {"type": 2, "text": "hello"}
    restored = Segment.from_dict(d)
    assert isinstance(restored, TextSegment)
    assert restored.text == "hello"


def test_image_segment():
    from easybot_mcdr.message import ImageSegment, SegmentType, Segment
    seg = ImageSegment("https://example.com/img.png")
    assert seg.type == SegmentType.IMAGE
    d = seg.to_dict()
    restored = Segment.from_dict(d)
    assert isinstance(restored, ImageSegment)
    assert restored.url == "https://example.com/img.png"


def test_file_segment():
    from easybot_mcdr.message import FileSegment, SegmentType, Segment
    seg = FileSegment("https://example.com/file.pdf", name="doc.pdf")
    d = seg.to_dict()
    restored = Segment.from_dict(d)
    assert isinstance(restored, FileSegment)
    assert restored.file_url == "https://example.com/file.pdf"
    assert restored.name == "doc.pdf"


def test_at_segment():
    from easybot_mcdr.message import AtSegment, SegmentType, Segment
    seg = AtSegment("Steve")
    d = seg.to_dict()
    restored = Segment.from_dict(d)
    assert isinstance(restored, AtSegment)
    assert restored.at_user_name == "Steve"


def test_reply_segment():
    from easybot_mcdr.message import ReplySegment, SegmentType, Segment
    seg = ReplySegment("msg_123", text="original")
    d = seg.to_dict()
    restored = Segment.from_dict(d)
    assert isinstance(restored, ReplySegment)
    assert restored.message_id == "msg_123"
    assert restored.text == "original"


def test_segments_roundtrip():
    from easybot_mcdr.message import TextSegment, ImageSegment, AtSegment, segments_from_list, segments_to_list
    original = [TextSegment("hi"), ImageSegment("url"), AtSegment("Bob")]
    data = segments_to_list(original)
    restored = segments_from_list(data)
    assert len(restored) == 3
    assert restored[0].text == "hi"
    assert restored[1].url == "url"
    assert restored[2].at_user_name == "Bob"


# ── 4. 玩家 API 测试 ────────────────────────────────────────────────
def test_player_info_construction():
    from easybot_mcdr.api.player import PlayerInfo
    p = PlayerInfo("127.0.0.1", "Steve", "uuid-1234")
    assert p.ip == "127.0.0.1"
    assert p.name == "Steve"
    assert p.uuid == "uuid-1234"


def test_offline_uuid_generation():
    from easybot_mcdr.api.player import generate_offline_uuid
    uuid = generate_offline_uuid("Steve")
    assert isinstance(uuid, str)
    assert len(uuid) == 36
    assert uuid.count("-") == 4


def test_offline_uuid_deterministic():
    from easybot_mcdr.api.player import generate_offline_uuid
    uuid1 = generate_offline_uuid("TestPlayer")
    uuid2 = generate_offline_uuid("TestPlayer")
    assert uuid1 == uuid2, "UUID 生成应具有确定性"


def test_offline_uuid_different_names():
    from easybot_mcdr.api.player import generate_offline_uuid
    uuid1 = generate_offline_uuid("Player1")
    uuid2 = generate_offline_uuid("Player2")
    assert uuid1 != uuid2, "不同名称应生成不同 UUID"


def test_player_data_map():
    from easybot_mcdr.api.player import get_data_map
    dm = get_data_map()
    assert "online_players" in dm
    assert "uuid_map" in dm
    assert "cache" in dm


# ── 5. 假人过滤测试 ─────────────────────────────────────────────────
def test_bot_filter_matching():
    """测试假人前缀匹配逻辑。"""
    prefixes = ["Bot_", "BOT_", "bot_"]
    assert any("Bot_Steve".startswith(p) for p in prefixes)
    assert any("BOT_Creeper".startswith(p) for p in prefixes)
    assert any("bot_Zombie".startswith(p) for p in prefixes)
    assert not any("Steve".startswith(p) for p in prefixes)
    assert not any("Notch".startswith(p) for p in prefixes)


def test_bot_filter_disabled():
    """假人过滤禁用时，不应过滤任何玩家。"""
    prefixes = ["Bot_", "BOT_", "bot_"]
    enabled = False

    def is_bot(player):
        if not enabled:
            return False
        return any(player.startswith(p) for p in prefixes)

    assert not is_bot("Bot_Steve")
    assert not is_bot("Steve")


# ── 6. Prefix Handler 测试 ──────────────────────────────────────────
def test_prefix_handler_creation():
    from easybot_mcdr.impl.prefix_handler import PrefixNameHandler
    handler = PrefixNameHandler()
    assert handler.get_name() == "easybot_prefix_handler"


def test_prefix_handler_parse_chat():
    """测试 PrefixNameHandler 可识别的标准服务器输出格式。"""
    from easybot_mcdr.impl.prefix_handler import PrefixNameHandler
    handler = PrefixNameHandler()
    info = handler.parse_server_stdout(
        "[12:00:00] [Server thread/INFO]: <Steve> Hello world"
    )
    assert info is not None
    assert info.player == "Steve"
    assert "Hello world" in info.content


# ── 7. RPC 注册表测试 ───────────────────────────────────────────────
def test_rpc_decorator_registration():
    import easybot_mcdr.impl.rpc_handlers
    from easybot_mcdr.rpc import _registry
    assert len(_registry) > 0, "未注册任何 RPC 处理器"


def test_rpc_expected_ops():
    import easybot_mcdr.impl.rpc_handlers
    from easybot_mcdr.rpc import _registry
    expected = {"PING", "RUN_COMMAND", "KICK_PLAYER",
                "SYNC_CHAT", "GET_PLAYER_LIST", "SYNC_SEGMENTS"}
    registered = set(_registry.keys())
    missing = expected - registered
    assert not missing, f"缺少 RPC 处理器: {missing}"


# ── 8. EventBus 测试 ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_event_bus_register_and_emit():
    from easybot_mcdr.event_bus import EventBus
    eb = EventBus()
    called = []

    @eb.on("test_event")
    def handler(**kwargs):
        called.append(kwargs.get("value"))

    await eb.emit("test_event", value=42)
    assert called == [42]


@pytest.mark.asyncio
async def test_event_bus_priority():
    from easybot_mcdr.event_bus import EventBus
    eb = EventBus()
    order = []

    @eb.on("prio", priority=10)
    def high(**kw):
        order.append("high")

    @eb.on("prio", priority=1)
    def low(**kw):
        order.append("low")

    await eb.emit("prio")
    assert order == ["high", "low"], f"优先级顺序错误: {order}"
