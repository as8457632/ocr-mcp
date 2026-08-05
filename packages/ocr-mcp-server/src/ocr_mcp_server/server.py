"""构建服务端 MCP Server：暴露 ocr_image 工具。"""

from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool
from openai import AsyncOpenAI

from .config import ServerConfig
from .ocr import MODE_PLAIN, SUPPORTED_MODES, run_ocr

OCR_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "image": {
            "type": "string",
            "description": "图片内容：data URI（data:image/...;base64,...）或 http(s):// 图片 URL",
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


def create_server(config: ServerConfig) -> Server:
    """创建 MCP Server，持有模型客户端并注册 ocr_image 工具。"""
    client = AsyncOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=config.timeout,
    )
    server = Server(
        "ocr-mcp-server",
        instructions="基于多模态模型的 OCR 识别服务。调用 ocr_image 识别图片中的文字。",
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="ocr_image",
                description="识别图片中的全部文字。",
                inputSchema=OCR_IMAGE_SCHEMA,
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> dict:
        if name != "ocr_image":
            raise ValueError(f"未知工具: {name}")
        image = arguments.get("image")
        prompt = arguments.get("prompt")
        mode = arguments.get("mode") or MODE_PLAIN
        if not isinstance(image, str) or not image:
            raise ValueError("参数 image 缺失或为空")
        if prompt is not None and not isinstance(prompt, str):
            raise ValueError("参数 prompt 必须是字符串")
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"参数 mode 必须是 {' 或 '.join(SUPPORTED_MODES)} 之一")
        text = await run_ocr(client, config.model, image, prompt, mode)
        return {"text": text}

    return server
