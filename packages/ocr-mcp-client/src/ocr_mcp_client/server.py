"""构建客户端 MCP Server：本地图片转 base64 后转发给服务端。"""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from .config import ClientConfig
from .remote import call_remote_ocr

SUPPORTED_MODES = ("plain", "structured")

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif",
}
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

# 纯 base64 至少约对应几十字节图片，避免把短字符串误判为 base64
_MIN_RAW_BASE64_LEN = 64
_RAW_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")

OCR_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "image": {
            "type": "string",
            "description": (
                "图片来源：本地文件路径、http(s):// URL、"
                "data URI（data:image/...;base64,...），或纯 base64 图片数据"
            ),
        },
        "prompt": {
            "type": ["string", "null"],
            "description": "自定义识别提示词（可选），默认按 OCR 场景优化",
        },
        "mode": {
            "type": "string",
            "enum": list(SUPPORTED_MODES),
            "description": "识别模式：plain 保持排版输出纯文本；structured 输出 Markdown 结构化文本",
        },
    },
    "required": ["image"],
    "additionalProperties": False,
}


def file_to_data_uri(path_str: str) -> str:
    """读取本地图片文件并转换为 base64 data URI。"""
    path = Path(path_str).expanduser()
    if not path.is_file():
        raise ValueError(f"图片文件不存在: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"不支持的图片格式: {suffix or '(无扩展名)'}，支持: {supported}"
        )
    data = path.read_bytes()
    if not data:
        raise ValueError(f"图片文件为空: {path}")
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{MIME_TYPES[suffix]};base64,{encoded}"


def _looks_like_filesystem_path(image: str) -> bool:
    """判断是否像本地文件路径（优先于纯 base64，因 base64 也可含 '/'）。"""
    s = image.strip()
    if not s:
        return False
    if s.startswith(("/", "~/", "./", "../", "~\\")):
        return True
    # Windows: C:\... 或 C:/...
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] in "/\\":
        return True
    if "\\" in s:
        return True
    # 相对路径常带扩展名，如 shot.png
    return Path(s).suffix.lower() in SUPPORTED_EXTENSIONS


def _looks_like_raw_base64(image: str) -> bool:
    """粗判是否为纯 base64 图片数据（非路径、非 URL、非 data URI）。"""
    if _looks_like_filesystem_path(image):
        return False
    compact = "".join(image.split())
    if len(compact) < _MIN_RAW_BASE64_LEN:
        return False
    if not _RAW_BASE64_RE.fullmatch(compact):
        return False
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return False
    return bool(decoded)


def to_server_image(image: str) -> str:
    """将用户输入归一化为服务端可用的图片表示。

    支持：data URI、http(s) URL、纯 base64、本地文件路径。
    """
    stripped = image.strip()
    if stripped.startswith("data:") and ";base64," in stripped:
        return stripped
    if stripped.startswith(("http://", "https://")):
        return stripped
    if _looks_like_filesystem_path(stripped):
        return file_to_data_uri(stripped)
    if _looks_like_raw_base64(stripped):
        compact = "".join(stripped.split())
        return f"data:image/png;base64,{compact}"
    return file_to_data_uri(stripped)


def source_label(image: str) -> str:
    """生成返回给调用方的 source 标签，避免把整段 base64 回传。"""
    stripped = image.strip()
    if stripped.startswith("data:") and ";base64," in stripped:
        mime = stripped[5:].split(";", 1)[0] or "image"
        return f"data:{mime};base64,..."
    if _looks_like_raw_base64(stripped):
        return "base64:..."
    return image


def create_server(config: ClientConfig) -> Server:
    """创建客户端 MCP Server，注册 ocr_image 工具。"""
    server = Server(
        "ocr-mcp-client",
        instructions=(
            "将本地路径、URL 或 base64/data URI 图片转发给远端 OCR MCP 服务进行文字识别。"
        ),
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="ocr_image",
                description=(
                    "识别图片中的全部文字。"
                    "image 可为本地路径、http(s) URL、data URI 或纯 base64，无需先落盘。"
                ),
                inputSchema=OCR_IMAGE_SCHEMA,
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> dict:
        if name != "ocr_image":
            raise ValueError(f"未知工具: {name}")
        image = arguments.get("image")
        prompt = arguments.get("prompt")
        mode = arguments.get("mode") or "plain"
        if not isinstance(image, str) or not image:
            raise ValueError("参数 image 缺失或为空")
        if prompt is not None and not isinstance(prompt, str):
            raise ValueError("参数 prompt 必须是字符串")
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"参数 mode 必须是 {' 或 '.join(SUPPORTED_MODES)} 之一")

        server_image = to_server_image(image)
        result = await call_remote_ocr(
            server_url=config.server_url,
            image=server_image,
            prompt=prompt,
            mode=mode,
            token=config.server_token,
            timeout=config.timeout,
        )
        result["source"] = source_label(image)
        return result

    return server
