import re
from mcdreforged.handler.impl.vanilla_handler import VanillaHandler


class PrefixNameHandler(VanillaHandler):
    """复合服务器处理器：尝试多种内置 handler 解析，支持前缀格式玩家名"""

    def get_name(self) -> str:
        return 'easybot_prefix_handler'

    def _get_handler_classes(self):
        classes = []
        for name in ('ForgeHandler', 'FabricHandler', 'SpigotHandler',
                      'PaperHandler', 'VanillaHandler'):
            try:
                mod = __import__('mcdreforged.handler.impl',
                                 fromlist=[name])
                classes.append(getattr(mod, name))
            except (ImportError, AttributeError):
                continue
        return classes

    def parse_server_stdout(self, text: str):
        handlers = self._get_handler_classes()
        info = None
        for cls in handlers:
            attr = f'_eb_{cls.__name__}'
            parser = getattr(self, attr, None)
            if parser is None:
                try:
                    parser = cls()
                except Exception:
                    continue
                setattr(self, attr, parser)
            try:
                result = parser.parse_server_stdout(text)
                if result is not None:
                    info = result
                    if getattr(result, 'player', None):
                        break
            except Exception:
                continue

        if info is None:
            info = super().parse_server_stdout(text)

        # 前缀解析: <[Prefix]PlayerName> Message
        if info.player is None:
            m = re.fullmatch(
                r'(?:\[Not Secure\] )?<\[(?P<prefix>[^\]]+)\]'
                r'(?P<name>[^>]+)> (?P<message>.*)',
                info.content
            )
            if m and self._verify_player_name(m['name']):
                info.player = m['name']
                info.content = m['message']
        return info
