import os
import random
import socket
import logging

logger = logging.getLogger("EasyBot")

_server_dir = None


def _get_server_dir() -> str:
    global _server_dir
    if _server_dir:
        return _server_dir
    try:
        from mcdreforged.api.types import ServerInterface
        server = ServerInterface.psi()
        _server_dir = server.get_mcdr_config().get("working_directory", ".")
    except Exception:
        _server_dir = "."
    return _server_dir


def _get_server_prop_path() -> str:
    return os.path.join(_get_server_dir(), "server.properties")


def _is_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("localhost", port)) != 0
    except Exception:
        return False


def get_available_port(port: int) -> int:
    if _is_port_available(port):
        return port
    for _ in range(50):
        new_port = port + random.randint(-100, 100)
        if 1024 <= new_port <= 65535 and _is_port_available(new_port):
            return new_port
    return port


def read_server_properties() -> dict:
    props = {}
    prop_path = _get_server_prop_path()
    if not os.path.exists(prop_path):
        return props
    try:
        with open(prop_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    props[key.strip()] = value.strip()
    except Exception as e:
        logger.error(f"读取 server.properties 失败: {e}")
    return props


def write_server_properties(props: dict):
    try:
        prop_path = _get_server_prop_path()
        lines = []
        for key, value in props.items():
            lines.append(f"{key}={value}")
        with open(prop_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("server.properties 已更新")
    except Exception as e:
        logger.error(f"写入 server.properties 失败: {e}")


def check_rcon_config(server) -> dict:
    result = {
        "rcon_enabled": False,
        "rcon_port": 25575,
        "rcon_password": "",
        "mcdr_rcon_enabled": False,
        "server_rcon_enabled": False,
        "server_rcon_port": 25575,
        "port_mismatch": False,
        "needs_config": False,
    }

    try:
        mcdr_config = server.get_mcdr_config()
        rcon_cfg = mcdr_config.get("rcon", {})
        result["mcdr_rcon_enabled"] = rcon_cfg.get("enable", False)
        result["rcon_port"] = rcon_cfg.get("port", 25575)
        result["rcon_password"] = rcon_cfg.get("password", "")
    except Exception:
        pass

    props = read_server_properties()
    result["server_rcon_enabled"] = props.get("enable-rcon", "false").lower() == "true"
    result["server_rcon_port"] = int(props.get("rcon.port", 25575))

    result["rcon_enabled"] = result["mcdr_rcon_enabled"] and result["server_rcon_enabled"]

    if result["rcon_enabled"] and result["rcon_port"] != result["server_rcon_port"]:
        result["port_mismatch"] = True
        result["rcon_enabled"] = False

    if not result["rcon_enabled"]:
        result["needs_config"] = True

    return result


def test_rcon_connection(server) -> bool:
    try:
        result = server.rcon_query("list")
        return result is not None
    except Exception:
        return False


def auto_configure_rcon(server, port: int = 25575, password: str = "") -> bool:
    # 优先级1: RCON 已经在运行，直接同步当前连接信息到 MCDR
    if server.is_rcon_running():
        mcdr_cfg = server.get_mcdr_config().get("rcon", {})
        mcdr_port = mcdr_cfg.get("port", 25575)
        mcdr_password = mcdr_cfg.get("password", "")
        try:
            server.modify_mcdr_config({
                "rcon.enable": True,
                "rcon.port": mcdr_port,
                "rcon.password": mcdr_password,
            })
            logger.info(f"RCON 已在运行，同步 MCDR 配置: port={mcdr_port}")
            return True
        except Exception as e:
            logger.error(f"同步 RCON 配置失败: {e}")
            return False

    props = read_server_properties()
    props_rcon_enabled = props.get("enable-rcon", "").lower() == "true"

    # 优先级2: server.properties 已配置 RCON，同步到 MCDR
    if props_rcon_enabled:
        server_port = int(props.get("rcon.port", 25575))
        server_password = props.get("rcon.password", "")

        try:
            server.modify_mcdr_config({
                "rcon.enable": True,
                "rcon.port": server_port,
                "rcon.password": server_password,
            })
            logger.info(f"已从 server.properties 同步 RCON 配置到 MCDR: port={server_port}")
            return True
        except Exception as e:
            logger.error(f"同步 RCON 配置失败: {e}")
            return False

    # 优先级3: 完全未配置，自动生成
    try:
        import secrets
        if not password:
            password = secrets.token_urlsafe(16)

        available_port = get_available_port(port)

        try:
            server.modify_mcdr_config({
                "rcon.enable": True,
                "rcon.port": available_port,
                "rcon.password": password,
            })
            logger.info(f"MCDR RCON 配置已更新: port={available_port}")
        except Exception as e:
            logger.error(f"更新 MCDR RCON 配置失败: {e}")
            return False

        props["enable-rcon"] = "true"
        props["rcon.port"] = str(available_port)
        props["rcon.password"] = password
        write_server_properties(props)

        logger.info(f"RCON 自动配置完成: port={available_port}，请重启服务器生效")
        return True

    except Exception as e:
        logger.error(f"RCON 自动配置失败: {e}")
        return False


def get_rcon_config_tips() -> str:
    return (
        "RCON 未配置，部分功能（命令执行、NBT读取）可能受限。\n"
        "请使用 !!ez rcon auto 自动配置。"
    )
