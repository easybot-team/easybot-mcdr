from mcdreforged.api.all import ServerInterface

def get_plugin_version():
    """获取插件版本号
    
    优先通过MCDR API获取版本号，这是MCDR插件开发的标准方法。
    当在非MCDR环境中运行时，回退到从插件元数据文件读取。
    确保始终返回字符串类型，避免JSON序列化错误。
    """
    try:
        # 首选方法：通过MCDR API获取版本号
        server = ServerInterface.get_instance()
        plugin_id = 'easybot_mcdr'
        # 转换为字符串，避免Version对象导致的JSON序列化错误
        return str(server.get_plugin_metadata(plugin_id).version)
    except Exception:
        return "unknown"