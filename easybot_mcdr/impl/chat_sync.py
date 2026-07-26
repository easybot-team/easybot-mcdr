from mcdreforged.api.all import *
from easybot_mcdr.config import get_config


async def on_user_info(server: PluginServerInterface, info: Info):
    if info.player is None:
        return
    if (
        info.content.startswith("!!")
        and get_config()["message_sync"]["ignore_mcdr_command"]
    ):
        return
    from easybot_mcdr.main import wsc

    # 检测 ChatImage CICode/CQCode，替换 file:// 为网络 URL
    from easybot_mcdr.impl.chat_image import parse_chat_image, strip_image_codes, replace_file_urls
    from easybot_mcdr.config import get_config as _cfg
    cfg = _cfg().get("image_upload", {})
    if cfg.get("enabled"):
        info.content = replace_file_urls(info.content)
    images = parse_chat_image(info.content)

    if images:
        # 有图片: 发送文本部分 + IMAGE segments
        text_part = strip_image_codes(info.content)
        extra = []
        if text_part:
            extra.append({"type": 2, "text": text_part})
        for url, name in images:
            extra.append({"type": 3, "url": url, "summary": name})
        await _push_resolved_message(info.player, text_part or "", False, extra=extra)
    else:
        await _push_resolved_message(info.player, info.content, False)


async def _push_resolved_message(raw_player: str, message: str, use_command: bool, extra: list = None):
    """
    上报前通过 UUID 锚点反查真实名，确保中心服务能匹配到绑定关系。
    模组改写聊天名时，info.player 可能是 [VIP]Steve 这类显示名，
    这里还原为 join 时锚定的真实名 Steve 及其 UUID，与名字解耦。
    """
    from easybot_mcdr.api.player import resolve_player, add_alias
    from easybot_mcdr.main import wsc

    real_name, uuid = resolve_player(raw_player)
    # 若解析名与真实名不同，记录为别名，便于后续反查命中
    if uuid and real_name and real_name != raw_player:
        add_alias(uuid, raw_player)

    # debug 输出：上报聊天信息前的关键内容（真实名/UUID/原始名/消息/extra）
    try:
        _logger = ServerInterface.get_instance().logger
        _logger.debug(
            f"[EasyBot] 上报聊天消息 -> raw_player={raw_player!r} "
            f"real_name={real_name!r} uuid={uuid!r} "
            f"message={message!r} use_command={use_command} extra={extra!r}"
        )
    except Exception:
        pass

    # push_message 内部会调 build_player_info(real_name) 取到锚定的 UUID
    await wsc.push_message(real_name, message, use_command, extra=extra)


async def cross_server_say(source: CommandSource, context: CommandContext):
    if not source.is_player:
        source.reply("§c这个命令只能由玩家使用!")
        return
    player = source.player
    message = context["message"]
    from easybot_mcdr.main import wsc
    await wsc.push_cross_server_message(player, message)
    source.reply("§a你的消息已发送到其他服务器.")
