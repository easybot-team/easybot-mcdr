from easybot_mcdr.config import get_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *


@EasyBotWsClient.listen_exec_op("UN_BIND_NOTIFY")
async def exec_un_bind_notify(ctx: ExecContext, data: dict, _):
    logger = ServerInterface.get_instance().logger
    player_name = data["player_name"]
    kick_message = data["kick_message"]
    logger.info(f"收到广播,玩家{player_name}解绑 (如果在本服将被踢出)")

    if get_config()["events"]["un_bind"]["exec_command"]:
        commands = get_config()["events"]["un_bind"]["comamnds"]
        logger.info(f"即将执行解绑预设指令 ({len(commands)}个)")
        for command in commands:
            ServerInterface.get_instance().execute(
                command.replace("#player", player_name)
            )

    if not get_config()["events"]["un_bind"]["kick"]:
        return
    
    if get_config()["events"]["un_bind"]["remove_white_list"] and is_white_list_enable():
        try:
            ServerInterface.get_instance().execute("whitelist remove " + player_name)
        except Exception as e:
            logger.error(f"移除白名单失败: {e}")

    from easybot_mcdr.impl.player_events import _push_kick
    _push_kick(player_name, "您已从聊群或管理平台解除账户绑定")
