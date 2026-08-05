"""构建客户端 MCP Server：本地图片转 base64 后转发给服务端。"""

from __future__ import annotations

import base64
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

OCR_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "image": {
            "type": "string",
            "description": "本地图片文件路径或 http(s):// 图片 URL",
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


def to_server_image(image: str) -> str:
    """将用户输入归一化为服务端可用的图片表示：URL 原样透传，本地路径转 data URI。"""
    if image.startswith(("http://", "https://")):
        return image
    return file_to_data_uri(image)


def create_server(config: ClientConfig) -> Server:
    """创建客户端 MCP Server，注册 ocr_image 工具。"""
    server = Server(
        "ocr-mcp-client",
        instructions="将本地图片转发给远端 OCR MCP 服务进行文字识别。",
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="ocr_image",
                description="识别图片中的全部文字。传入本地图片路径或图片 URL。",
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
        result["source"] = image
        return result

    return server
