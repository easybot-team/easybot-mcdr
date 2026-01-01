import json
import os
from mcdreforged.api.all import *

config = {}

def load_config(server: PluginServerInterface):
    global config
    server.logger.info("加载配置中...")
    config_path = server.get_data_folder()
    os.makedirs(config_path, exist_ok=True)
    config_file_path = os.path.join(config_path, "config.json")
    
    # 用户配置文件路径
    user_config_path = os.path.join("plugins", "easybot-mcdr-main", "config.json")
    
    try:
        # 优先尝试加载用户配置文件
        if os.path.exists(user_config_path):
            server.logger.info(f"检测到用户配置文件: {user_config_path}")
            with open(user_config_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
            
            # 保存用户配置到插件目录
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            server.logger.info(f"用户配置已保存到: {config_file_path}")
        else:
            # 没有用户配置则使用默认配置
            if not os.path.exists(config_file_path):
                with server.open_bundled_file("data/config.json") as data:
                    with open(config_file_path, "w", encoding="utf-8", newline='') as f:
                        f.write(data.read().decode("utf-8-sig"))
                    server.logger.info("配置文件不存在，已创建默认配置文件")
            
            # 加载配置文件
            with open(config_file_path, "r", encoding="utf-8-sig", newline='') as f:
                config = json.load(f)
        
        # 验证和修复配置
        if "events" in config:
            for event_type, event_config in config["events"].items():
                if "comamnds" in event_config and not isinstance(event_config["comamnds"], list):
                    server.logger.warning(f"修复事件 {event_type} 的命令列表格式")
                    event_config["comamnds"] = []
        
        # 确保bot_filter存在
        if "bot_filter" not in config:
            config["bot_filter"] = {
                "enabled": True,
                "prefixes": ["Bot_", "BOT_", "bot_"]
            }
            save_config(server)

        # 确保踢出延迟配置存在
        if "kick_delay_seconds" not in config:
            config["kick_delay_seconds"] = 5
            save_config(server)
            
        server.logger.info(f"配置文件路径: {config_file_path}")
        server.logger.info("配置文件加载成功")
        
    except json.JSONDecodeError as e:
        server.logger.error(f"配置文件解析失败: {e}")
        # 创建默认配置
        with server.open_bundled_file("data/config.json") as data:
            config = json.loads(data.read().decode("utf-8-sig"))
        server.logger.info("已恢复默认配置")
    
    # 如果缺少 bot_filter，动态添加默认值
    if "bot_filter" not in config:
        config["bot_filter"] = {
            "enabled": True,
            "prefixes": ["Bot_", "BOT_", "bot_"]
        }
        save_config(server)

def save_config(server: PluginServerInterface):
    config_path = server.get_data_folder()
    config_file_path = os.path.join(config_path, "config.json")
    with open(config_file_path, "w", encoding="utf-8", newline='') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    server.logger.info("配置文件已保存")

def get_config() -> dict:
    return config