from easybot_mcdr.config import get_config


def is_white_list_enable():
    return get_config()["enable_white_list"]
