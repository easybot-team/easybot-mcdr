import copy
import json
import os
import threading
from mcdreforged.api.all import *

_config = {}
_config_lock = threading.Lock()


def load_config(server: PluginServerInterface):
    global _config
    server.logger.info("加载配置中...")
    config_path = server.get_data_folder()
    os.makedirs(config_path, exist_ok=True)
    config_file_path = os.path.join(config_path, "config.json")

    user_config_path = os.path.join("plugins", "easybot-mcdr-main", "config.json")

    try:
        if os.path.exists(user_config_path):
            server.logger.info(f"检测到用户配置文件: {user_config_path}")
            with open(user_config_path, "r", encoding="utf-8-sig") as f:
                new_config = json.load(f)
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            server.logger.info(f"用户配置已保存到: {config_file_path}")
        else:
            if not os.path.exists(config_file_path):
                with server.open_bundled_file("data/config.json") as data:
                    with open(config_file_path, "w", encoding="utf-8", newline='') as f:
                        f.write(data.read().decode("utf-8-sig"))
                    server.logger.info("配置文件不存在，已创建默认配置文件")

            with open(config_file_path, "r", encoding="utf-8-sig", newline='') as f:
                new_config = json.load(f)

        with _config_lock:
            _config = new_config

        _validate_config(server)

    except json.JSONDecodeError as e:
        server.logger.error(f"配置文件解析失败: {e}")
        with server.open_bundled_file("data/config.json") as data:
            with _config_lock:
                _config = json.loads(data.read().decode("utf-8-sig"))
        server.logger.info("已恢复默认配置")

    _ensure_defaults(server)


def _validate_config(server: PluginServerInterface):
    with _config_lock:
        if "events" in _config:
            for event_type, event_config in _config["events"].items():
                if "comamnds" in event_config and not isinstance(event_config["comamnds"], list):
                    server.logger.warning(f"修复事件 {event_type} 的命令列表格式")
                    event_config["comamnds"] = []


def _ensure_defaults(server: PluginServerInterface):
    changed = False
    with _config_lock:
        if "bot_filter" not in _config:
            _config["bot_filter"] = {
                "enabled": True,
                "prefixes": ["Bot_", "BOT_", "bot_"]
            }
            changed = True
        if "kick_delay_seconds" not in _config:
            _config["kick_delay_seconds"] = 5
            changed = True
        if "handler" not in _config:
            _config["handler"] = {"enabled": True}
            changed = True
        if "image_upload" not in _config:
            _config["image_upload"] = {"enabled": False, "imgbb_api_key": ""}
            changed = True
    if changed:
        save_config(server)


def save_config(server: PluginServerInterface):
    config_path = server.get_data_folder()
    config_file_path = os.path.join(config_path, "config.json")
    with _config_lock:
        snapshot = copy.deepcopy(_config)
    with open(config_file_path, "w", encoding="utf-8", newline='') as f:
        json.dump(snapshot, f, indent=4, ensure_ascii=False)
    server.logger.info("配置文件已保存")


def get_config() -> dict:
    with _config_lock:
        return copy.deepcopy(_config)