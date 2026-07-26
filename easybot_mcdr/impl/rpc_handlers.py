from mcdreforged.api.all import ServerInterface
from easybot_mcdr.rpc import bridge_rpc, _registry
from easybot_mcdr.impl.bridge_behavior_impl import DefaultBridgeBehavior


def _behavior():
    server = ServerInterface.get_instance()
    return DefaultBridgeBehavior(server)


# ============================================================
# PING — MCDR 自有，bridge 无对应
# ============================================================
@bridge_rpc("PING", description="Health check")
async def ping(ctx, data, session_info):
    await ctx.callback({"success": True, "text": "pong"})


# ============================================================
# GET_EXTENSIONS — 对应 bridge 的 GET_EXTENSIONS
# 回调结构: { extensions: { <identifier>: { name, description, author, version, required_plugins, identifier, rpc } } }
#
# 注意: SEND_TO_CHAT / PLACEHOLDER_API_QUERY / UN_BIND_NOTIFY /
#       BIND_SUCCESS_NOTIFY / PLAYER_LIST / GET_SERVER_INFO / RUN_COMMAND
#       均已在 impl/ 下的独立模块中注册监听器，此处不再重复注册。
# ============================================================
@bridge_rpc("GET_EXTENSIONS", description="Get installed extensions")
async def get_extensions(ctx, data, session_info):
    """
    返回当前 MCDR 端已注册的扩展信息。
    严格按照 bridge 的 GET_EXTENSIONS 回调结构上报：每个扩展以 identifier 为 key，
    值为扁平结构 (name/description/author/version/required_plugins/identifier/rpc)。
    rpc 方法的值也按 bridge 格式 (identifier/method/description/displayName/fullMethodClassName)。
    不额外添加 success 字段，与 bridge 完全一致。
    """
    from easybot_mcdr.meta import get_plugin_version

    rpc_methods = {}
    for exec_op_key, handler in _registry.items():
        rpc_methods[exec_op_key] = {
            "identifier": "easybot-mcdr",
            "method": exec_op_key,
            "description": (getattr(handler, "__doc__", "") or "").strip(),
            "displayName": exec_op_key,
            "fullMethodClassName": f"easybot_mcdr.impl.rpc_handlers.{getattr(handler, '__name__', exec_op_key)}",
        }

    extension = {
        "name": "EasyBot MCDR",
        "description": "EasyBot MCDR 桥接插件",
        "author": "EasyBot",
        "version": get_plugin_version(),
        "required_plugins": [],
        "identifier": "easybot-mcdr",
        "rpc": rpc_methods,
    }

    extensions = {"easybot-mcdr": extension}
    await ctx.callback({"extensions": extensions})


# ============================================================
# MODULE_INSTALLED — 对应 bridge 的 MODULE_INSTALLED
# 请求字段: module_name (String)  ← bridge 用 module_name，不是 name
# 回调结构: { installed (bool) }  ← bridge 用 installed，不是 result
# ============================================================
@bridge_rpc("MODULE_INSTALLED", description="Check if a module/plugin is installed")
async def module_installed(ctx, data, session_info):
    name = data.get("module_name") or data.get("name") or ""
    await ctx.callback({"installed": _behavior().module_is_installed(name)})


# ============================================================
# MODULE_ENABLED — 对应 bridge 的 MODULE_ENABLED
# 请求字段: module_name (String)
# 回调结构: { enabled (bool) }
# ============================================================
@bridge_rpc("MODULE_ENABLED", description="Check if a module/plugin is enabled")
async def module_enabled(ctx, data, session_info):
    name = data.get("module_name") or data.get("name") or ""
    await ctx.callback({"enabled": _behavior().module_is_enabled(name)})


# ============================================================
# IS_AUTHENTICATED — 对应 bridge 的 IS_AUTHENTICATED
# 请求字段: player_name (String)
# 回调结构: { authenticated (bool) }  ← bridge 用 authenticated，不是 result
#
# MCDR 端不维护玩家认证/绑定状态，始终返回 False。
# 主程序应通过 GET_SOCIAL_ACCOUNT 等接口自行查询。
# ============================================================
@bridge_rpc("IS_AUTHENTICATED", description="Check if a player is authenticated/bound")
async def is_authenticated(ctx, data, session_info):
    player_name = data.get("player_name") or ""
    await ctx.callback({"authenticated": _behavior().is_authenticated(player_name)})


# ============================================================
# GET_PLAYER_SKIN — 对应 bridge 的 GET_PLAYER_SKIN
# 请求字段: player_name (String)
# 回调结构: { message (String), result (int), skin_url (String, 可选), cape_url (String, 可选) }
# 注意: bridge 不发 success 字段
# ============================================================
@bridge_rpc("GET_PLAYER_SKIN", description="Get player skin URL")
async def get_player_skin(ctx, data, session_info):
    player_name = data.get("player_name") or ""
    skin_data = _behavior().get_player_skin(player_name)
    if skin_data:
        callback_data = {
            "message": "found",
            "result": 1,  # GetPlayerSkinResult.Succeeded
            "skin_url": skin_data.get("skin_url", ""),
        }
        cape = skin_data.get("cape_url")
        if cape:
            callback_data["cape_url"] = cape
        await ctx.callback(callback_data)
    else:
        await ctx.callback({
            "message": "not found",
            "result": 2  # GetPlayerSkinResult.Notfound
        })


# ============================================================
# READ_NBT_DATA — 对应 bridge 的 READ_NBT_DATA
# 请求字段: player_uuid (String), data_type (int/String)
# 回调结构: { message (String), result (int), data (JsonObject, 可选) }
# 注意: bridge 不发 success 字段
# ============================================================
@bridge_rpc("READ_NBT_DATA", description="Read player NBT data (0=PlayerData, 1=Advancements, 2=Statistics)")
async def read_nbt_data(ctx, data, session_info):
    player_uuid = data.get("player_uuid") or ""
    data_type = data.get("data_type", 0)

    DATA_TYPE_MAP = {
        "PlayerData": 0,
        "Advancements": 1,
        "Statistics": 2,
        "playerdata": 0,
        "advancements": 1,
        "statistics": 2,
    }
    if isinstance(data_type, str):
        data_type = DATA_TYPE_MAP.get(data_type, 0)

    try:
        result = _behavior().read_nbt_data(player_uuid, data_type)
        if result is None:
            await ctx.callback({
                "message": "not found",
                "result": 2  # ReadNbtResult.Notfound
            })
        else:
            parsed_data = result.get("parsed", {})
            await ctx.callback({
                "message": "found",
                "result": 1,  # ReadNbtResult.Succeeded
                "data": parsed_data
            })
    except Exception as e:
        await ctx.callback({
            "message": str(e),
            "result": 3  # ReadNbtResult.Error
        })
