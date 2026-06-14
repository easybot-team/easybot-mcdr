from mcdreforged.api.all import *
from mcdreforged.command.command_source import CommandSource
from easybot_mcdr.rpc import bridge_rpc


class _OutputCaptureSource(CommandSource):
    """自定义命令源, 捕获 reply() 输出用于获取 MCDR 命令执行结果"""

    def __init__(self, server):
        self._server = server.as_basic_server_interface()
        self._output = []

    def get_server(self):
        return self._server

    def get_permission_level(self):
        return 4  # CONSOLE level (highest)

    def reply(self, text, **kwargs):
        self._output.append(str(text))

    def get_output(self) -> str:
        return "\n".join(self._output) if self._output else ""


def _is_mcdr_command(command: str) -> bool:
    """判断是否为 MCDR 命令 (以 !! 开头)"""
    return command.strip().startswith("!!")


async def _execute_mcdr_command_with_output(server, command: str) -> str:
    """
    执行 MCDR 命令并捕获输出。

    原理:
    - 创建一个 _OutputCaptureSource 作为命令源
    - 通过 server.execute_command() 将命令送入 MCDR 命令树
    - 命令处理器调用 source.reply() 时, 输出被 _OutputCaptureSource 捕获
    - 返回捕获到的输出文本
    """
    source = _OutputCaptureSource(server)
    try:
        server.execute_command(command, source)
        output = source.get_output()
        return output if output else "(MCDR 命令已执行, 无输出)"
    except Exception as e:
        return f"(MCDR 命令执行失败: {e})"


@bridge_rpc("RUN_COMMAND", description="Execute a command on the server")
async def run_command(ctx, data, session_info):
    server = ServerInterface.get_instance()
    logger = server.logger

    command = data["command"]

    # Placeholder 变量替换
    if data.get("enable_papi"):
        from easybot_mcdr.impl.papi import run_placeholder
        command = await run_placeholder(command, data["player_name"])

    try:
        if _is_mcdr_command(command):
            # ========================================
            # MCDR 命令处理 (!! 开头的命令)
            # ========================================
            # MCDR 命令不会到达服务端, 而是由 MCDR CommandManager 处理
            # 使用 OutputCaptureSource 捕获 source.reply() 输出
            logger.debug(f"检测到 MCDR 命令 -> {command}")

            output = await _execute_mcdr_command_with_output(server, command)

            logger.debug(f"MCDR 命令执行完成, 输出: {output}")
            await ctx.callback({
                "success": True,
                "text": output
            })
        else:
            # ========================================
            # 服务端命令处理 (非 !! 开头的命令)
            # ========================================
            # 服务端命令需要 RCON 来执行并获取输出
            if not server.is_rcon_running():
                logger.error(f"RCON 未开启, 无法执行服务端命令 -> {command}")
                await ctx.callback({
                    "success": False,
                    "text": "目标 MCDR 未开启 RCON, 无法执行命令!"
                })
                return

            # 通过 RCON 执行命令并获取输出
            resp = server.rcon_query(command)
            logger.debug(f"执行服务端命令 -> {command}")
            logger.debug(f"执行结果 -> {resp}")
            await ctx.callback({
                "success": True,
                "text": resp if resp is not None else ""
            })

    except Exception as e:
        logger.warning(f"命令执行失败: {str(e)}")
        await ctx.callback({
            "success": False,
            "text": f"命令执行失败: {str(e)}"
        })
