from mcdreforged.api.all import ServerInterface
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from easybot_mcdr.impl.bridge_behavior_impl import DefaultBridgeBehavior


def _behavior():
    server = ServerInterface.get_instance()
    return DefaultBridgeBehavior(server)


@EasyBotWsClient.listen_exec_op("CROSS_BIND_NOTIFY")
async def on_cross_bind_notify(ctx: ExecContext, data: dict, _):
    """
    主程序推送跨平台绑定通知：玩家已在某平台绑定，现要在另一平台绑定。
    通知玩家在游戏内输入 !!ez confirm <code> 完成确认。
    """
    player_name = data.get("player_name", "")
    code = data.get("code", "")
    target_platform = data.get("target_platform", "")
    origin_platform = data.get("origin_platform", "")

    if not player_name:
        return

    _behavior().on_cross_bind_notify(player_name, code, target_platform, origin_platform)

    # bridge 对所有 exec_op（除 RPC_CALL 外）都会发送回调，CROSS_BIND_NOTIFY 不附加额外字段
    # 对应 bridge BridgeClient.handlePacket 末尾的 send(callBack)
    try:
        await ctx.callback({})
    except Exception:
        pass
