import time
from typing import Any, Dict, List
from easybot_mcdr.config import get_config
from easybot_mcdr.impl.chat_image import parse_chat_image, strip_image_codes
from easybot_mcdr.message import Segment, SegmentType, segments_from_list
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *


def _flatten_extra(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten nested extra arrays, extracting [[...]] image markers as IMAGE segments."""
    import re
    _DOUBLE_BRACKET = re.compile(r'\[\[(.+?)\]\]')

    def _is_img_marker(item: dict) -> bool:
        text = str(item.get("text", ""))
        ce = item.get("clickEvent")
        return (
            _DOUBLE_BRACKET.search(text)
            and isinstance(ce, dict)
            and ce.get("action") == "open_url"
        )

    result = []
    for item in data:
        if not isinstance(item, dict):
            result.append(item)
            continue

        nested = item.get("extra")
        if isinstance(nested, list) and nested:
            has_img = any(_is_img_marker(x) for x in nested if isinstance(x, dict))
            if has_img:
                for x in nested:
                    if not isinstance(x, dict):
                        if isinstance(x, str) and x:
                            result.append({"type": SegmentType.TEXT, "text": x})
                        continue
                    if _is_img_marker(x):
                        url = x.get("clickEvent", {}).get("value", "")
                        m = _DOUBLE_BRACKET.search(str(x.get("text", "")))
                        summary = m.group(1) if m else "图片"
                        result.append({"type": SegmentType.IMAGE, "url": url, "summary": summary})
                    else:
                        t = str(x.get("text", ""))
                        if t:
                            result.append({"type": SegmentType.TEXT, "text": t})
            else:
                result.extend(_flatten_extra(nested))
            continue

        text = item.get("text", "")
        if isinstance(text, str) and parse_chat_image(text):
            for url, name in parse_chat_image(text):
                result.append({"type": SegmentType.IMAGE, "url": url, "summary": name})
            clean = strip_image_codes(text)
            if clean:
                result.append({"type": SegmentType.TEXT, "text": clean})
        else:
            result.append(item)
    return result


def render_segments(segments: List[Segment], text: str = ""):
    server = ServerInterface.get_instance()
    text_list = RTextList()
    at_players = []
    current_text = ""
    has_at_all = False
    has_cicode = False

    def flush_text():
        nonlocal current_text
        if current_text:
            text_list.append(RText(current_text))
            current_text = ""

    for seg in segments:
        t = seg.type

        if t == SegmentType.TEXT:
            current_text += seg.text

        else:
            flush_text()

            if t == SegmentType.IMAGE:
                url = getattr(seg, "url", "")
                summary = getattr(seg, "summary", None) or "图片"
                if url:
                    from easybot_mcdr.impl.chat_image import to_cicode
                    # 用纯字符串输出 CICode，确保 ChatImage 能解析
                    server.broadcast(to_cicode(url, summary))
                    has_cicode = True
                else:
                    el = RText(f"[{summary}]")
                    el.set_color(RColor.green)
                    text_list.append(el)

            elif t == SegmentType.AT:
                at_names = getattr(seg, "at_player_names", []) or []
                user_id = str(getattr(seg, "at_user_id", ""))
                user_name = str(getattr(seg, "at_user_name", ""))

                if user_id == "0":
                    at_text = RText("@全体成员")
                    has_at_all = True
                elif not at_names:
                    at_text = RText(user_name)
                else:
                    at_text = RText("@" + ",".join(at_names))

                at_text.set_color(RColor.gold)
                at_text.set_hover_text(f"社交账号: {user_name}({user_id})")
                for p in at_names:
                    if isinstance(p, str):
                        at_players.append(p)
                text_list.append(at_text)

            elif t == SegmentType.FILE:
                el = RText("[文件]")
                el.set_color(RColor.green)
                text_list.append(el)

            elif t == SegmentType.REPLY:
                el = RText("[回复某条消息]")
                el.set_color(RColor.gray)
                text_list.append(el)

            elif t == SegmentType.FACE:
                face_name = getattr(seg, "display_name", None) or "表情"
                el = RText(f"[{face_name}]")
                el.set_color(RColor.yellow)
                text_list.append(el)

    flush_text()
    # 有 CICode 时，剩余部分也用纯字符串广播，保持一致性
    if has_cicode:
        remaining = str(text_list)
        if remaining.strip():
            server.broadcast(remaining)
    else:
        server.broadcast(text_list)
    return at_players, has_at_all


def _execute_at_commands(at_players, has_at_all):
    config = get_config().get("events", {}).get("message", {}).get("on_at", {})
    logger = ServerInterface.get_instance().logger

    if not config.get("exec_command"):
        return
    commands = config.get("comamnds", [])
    if not isinstance(commands, list):
        logger.warning("命令列表格式无效，已跳过执行")
        return

    targets = ["@a"] if has_at_all else [
        p for p in at_players
        if _check_online(p)
    ]

    for player in targets:
        for command in commands:
            if not isinstance(command, str):
                continue
            try:
                cmd = command.replace("#player", player)
                ServerInterface.get_instance().execute(cmd)
            except Exception as e:
                logger.error(f"执行命令失败: {cmd} ({str(e)})")


def _execute_at_sound(at_players, has_at_all):
    config = get_config().get("events", {}).get("message", {}).get("on_at", {})
    logger = ServerInterface.get_instance().logger
    sound_cfg = config.get("sound", {})

    if not sound_cfg.get("play_sound"):
        return
    command = sound_cfg.get("run")
    if not isinstance(command, str):
        logger.warning("音效命令配置无效，已跳过")
        return

    count = sound_cfg.get("count", 1)
    interval = sound_cfg.get("interval_ms", 1000)

    targets = ["@a"] if has_at_all else [
        p for p in at_players
        if _check_online(p)
    ]

    for player in targets:
        for _ in range(count):
            try:
                ServerInterface.get_instance().execute(command.replace("#player", player))
            except Exception as e:
                logger.error(f"执行音效命令失败: {e}")
            time.sleep(interval / 1000)


def _check_online(player: str) -> bool:
    from easybot_mcdr.api.player import check_online
    return check_online(player)


@EasyBotWsClient.listen_exec_op("SEND_TO_CHAT")
async def sync_message(ctx: ExecContext, data: dict, _):
    if not isinstance(data, dict):
        ServerInterface.get_instance().logger.error("无效的消息数据格式")
        return

    text = str(data.get("text", ""))

    extra_data = data.get("extra")
    if not isinstance(extra_data, list):
        extra_data = []

    # Replace file:// URLs with network-accessible URLs (imgbb or local server)
    from easybot_mcdr.config import get_config as _cfg
    img_cfg = _cfg().get("image_upload", {})
    if img_cfg.get("enabled"):
        from easybot_mcdr.impl.chat_image import replace_file_urls, convert_file_url
        text = replace_file_urls(text)
        for item in extra_data:
            if isinstance(item, dict) and "url" in item:
                item["url"] = convert_file_url(str(item["url"]))
            if isinstance(item, dict) and "text" in item:
                item["text"] = replace_file_urls(str(item["text"]))

    if not extra_data:
        ServerInterface.get_instance().broadcast(text)
        ServerInterface.get_instance().logger.info(text)
        return

    # Flatten nested extra arrays to extract [[...]] image markers
    flat_data = _flatten_extra(extra_data)
    segments = segments_from_list(flat_data)
    at_players, has_at_all = render_segments(segments, text)

    _execute_at_commands(at_players, has_at_all)
    _execute_at_sound(at_players, has_at_all)
