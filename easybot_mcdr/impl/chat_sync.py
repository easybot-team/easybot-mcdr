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
        await wsc.push_message(info.player, text_part or "", False, extra=extra)
    else:
        await wsc.push_message(info.player, info.content, False)


async def cross_server_say(source: CommandSource, context: CommandContext):
    if not source.is_player:
        source.reply("§c这个命令只能由玩家使用!")
        return
    player = source.player
    message = context["message"]
    from easybot_mcdr.main import wsc
    await wsc.push_cross_server_message(player, message)
    source.reply("§a你的消息已发送到其他服务器.")
