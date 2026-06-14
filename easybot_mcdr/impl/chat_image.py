import json
import os
import re
import socket
import threading
import uuid
import http.server
import http.client
import mimetypes
from typing import List, Tuple, Optional


# ---------- Local HTTP Server ----------

_local_server = None
_local_server_lock = threading.Lock()


class _ImageFileHandler(http.server.BaseHTTPRequestHandler):
    """轻量 HTTP handler，只提供文件读取"""

    def do_GET(self):
        # URL 格式: /<random_token>/<encoded_path>
        parts = self.path.strip("/").split("/", 1)
        if len(parts) < 2:
            self.send_error(404)
            return
        file_path = parts[1]
        # 还原路径分隔符
        file_path = file_path.replace("__SLASH__", "/").replace("__BACK__", "\\")
        if not os.path.isfile(file_path):
            self.send_error(404)
            return
        try:
            content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def log_message(self, format, *args):
        pass  # 静默日志


def _get_local_ip() -> str:
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_local_image_server(port: int = 0):
    """启动本地图片服务器"""
    global _local_server
    with _local_server_lock:
        if _local_server is not None:
            return
        server = http.server.HTTPServer(("0.0.0.0", port), _ImageFileHandler)
        _local_server = server
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            from mcdreforged.api.all import ServerInterface
            ServerInterface.get_instance().logger.info(
                f"[EasyBot-IMG] 本地图片服务器已启动: http://{_get_local_ip()}:{server.server_address[1]}")
        except Exception:
            pass


def stop_local_image_server():
    global _local_server
    with _local_server_lock:
        if _local_server:
            _local_server.shutdown()
            _local_server = None


def _local_file_url(file_path: str) -> Optional[str]:
    """将本地文件路径转为本地 HTTP URL"""
    with _local_server_lock:
        if _local_server is None:
            return None
        port = _local_server.server_address[1]
    ip = _get_local_ip()
    # 编码路径: / → __SLASH__, \ → __BACK__
    encoded = file_path.replace("/", "__SLASH__").replace("\\", "__BACK__")
    token = uuid.uuid4().hex[:8]
    return f"http://{ip}:{port}/{token}/{encoded}"


# ---------- File URL Replacement ----------

def _upload_to_imgbb(file_path: str, api_key: str) -> Optional[str]:
    """上传到 imgbb 图床，返回网络 URL"""
    import base64
    import urllib.request
    import urllib.parse
    try:
        with open(file_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        data = urllib.parse.urlencode({"key": api_key, "image": img_data}).encode("utf-8")
        req = urllib.request.Request("https://api.imgbb.com/1/upload", data=data)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("success"):
                return result["data"]["url"]
    except Exception:
        pass
    return None


def convert_file_url(url: str) -> str:
    """将单个 file:// URL 转为可访问的网络 URL。非 file:// URL 原样返回。"""
    if not url.startswith("file://"):
        return url
    from mcdreforged.api.all import ServerInterface
    from easybot_mcdr.config import get_config
    logger = ServerInterface.get_instance().logger
    imgbb_key = get_config().get("image_upload", {}).get("imgbb_api_key", "")
    file_path = url[len("file://"):]
    if os.name == "nt" and len(file_path) > 2 and file_path[0] == "/" and file_path[2] == ":":
        file_path = file_path[1:]
    file_path = file_path.replace("\\", "/") if os.name == "nt" else file_path
    if not os.path.isfile(file_path):
        logger.info(f"[EasyBot-IMG] file not found: {file_path}")
        return url
    if imgbb_key:
        web_url = _upload_to_imgbb(file_path, imgbb_key)
        if web_url:
            logger.info(f"[EasyBot-IMG] imgbb url={web_url}")
            return web_url
    web_url = _local_file_url(file_path)
    if web_url:
        logger.info(f"[EasyBot-IMG] local url={web_url}")
        return web_url
    logger.info(f"[EasyBot-IMG] no upload method available")
    return url


def replace_file_urls(text: str) -> str:
    """将 CICode 中的 file:// URL 替换为可访问的 HTTP URL。
    有 imgbb key 时优先上传 imgbb，否则用本地服务器。
    """
    from mcdreforged.api.all import ServerInterface
    from easybot_mcdr.config import get_config
    logger = ServerInterface.get_instance().logger
    imgbb_key = get_config().get("image_upload", {}).get("imgbb_api_key", "")

    def _replace(m):
        url = m.group("url") or ""
        if not url.startswith("file://"):
            return m.group(0)
        file_path = url[len("file://"):]
        if os.name == "nt" and len(file_path) > 2 and file_path[0] == "/" and file_path[2] == ":":
            file_path = file_path[1:]
        file_path = file_path.replace("\\", "/") if os.name == "nt" else file_path
        if not os.path.isfile(file_path):
            logger.info(f"[EasyBot-IMG] file not found: {file_path}")
            return m.group(0)
        # 优先 imgbb
        if imgbb_key:
            web_url = _upload_to_imgbb(file_path, imgbb_key)
            if web_url:
                logger.info(f"[EasyBot-IMG] imgbb url={web_url}")
                return m.group(0).replace(url, web_url)
        # 回退到本地服务器
        web_url = _local_file_url(file_path)
        if web_url:
            logger.info(f"[EasyBot-IMG] local url={web_url}")
            return m.group(0).replace(url, web_url)
        logger.info(f"[EasyBot-IMG] no upload method available")
        return m.group(0)

    return _CICODE_PATTERN.sub(_replace, text)


# ---------- CICode Parsing ----------

_CICODE_PATTERN = re.compile(
    r'\[\[CICode,(?:.*?url=(?P<url>[^,\]]+).*?)?\]\]'
)

_CQCODE_PATTERN = re.compile(
    r'\[CQ:image,(?:.*?file=(?P<url>[^,\]]+).*?)?\]'
)

_IMAGE_URL_PATTERN = re.compile(
    r'https?://\S+\.(?:png|jpe?g|gif|bmp|ico|webp)(?:\?\S*)?',
    re.IGNORECASE
)


def parse_chat_image(text: str) -> List[Tuple[str, str]]:
    """从聊天文本中提取图片。返回 [(url, name), ...] 列表。"""
    results = []
    for m in _CICODE_PATTERN.finditer(text):
        url = m.group("url") or ""
        if url and not url.startswith("file://"):
            name_match = re.search(r'name=([^,\]]+)', m.group(0))
            name = name_match.group(1) if name_match else "图片"
            results.append((url, name))
    for m in _CQCODE_PATTERN.finditer(text):
        url = m.group("url") or ""
        if url and not url.startswith("file://"):
            results.append((url, "图片"))
    if not results:
        for m in _IMAGE_URL_PATTERN.finditer(text):
            url = m.group()
            if not url.startswith("file://"):
                results.append((url, "图片"))
    return results


def has_chat_image(text: str) -> bool:
    """检查文本中是否包含 ChatImage 图片"""
    if _CICODE_PATTERN.search(text):
        return True
    if _CQCODE_PATTERN.search(text):
        return True
    if not _CICODE_PATTERN.search(text) and not _CQCODE_PATTERN.search(text):
        if _IMAGE_URL_PATTERN.search(text):
            return True
    return False


def to_cicode(url: str, name: str = "图片") -> str:
    """将图片 URL 转为 CICode 格式，供 ChatImage 客户端渲染"""
    return f"[[CICode,url={url},name={name},nsfw=false]]"


def strip_image_codes(text: str) -> str:
    """移除文本中的 CICode/CQCode，保留纯文本部分"""
    result = _CICODE_PATTERN.sub("", text)
    result = _CQCODE_PATTERN.sub("", result)
    return result.strip()
