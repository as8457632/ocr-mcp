"""客户端调用远端 OCR MCP 服务。"""

from __future__ import annotations

import json

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent


def parse_result(result: CallToolResult) -> dict:
    """将远端工具调用结果解析为 {text}。

    优先使用 structuredContent，其次尝试解析 JSON 文本，最后原样返回文本。
    """
    text_parts = [
        block.text for block in result.content if isinstance(block, TextContent)
    ]
    raw_text = "\n".join(text_parts)

    if result.isError:
        raise RuntimeError(raw_text or "远端 OCR 服务返回错误")

    structured = result.structuredContent
    if isinstance(structured, dict):
        return {"text": str(structured.get("text", raw_text))}

    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        data = None
    if isinstance(data, dict):
        return {"text": str(data.get("text", raw_text))}
    return {"text": raw_text}


async def call_remote_ocr(
    server_url: str,
    image: str,
    prompt: str | None = None,
    mode: str = "plain",
    token: str | None = None,
    timeout: float = 60.0,
) -> dict:
    """通过 Streamable HTTP 调用远端 MCP 的 ocr_image 工具。"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    timeout_config = httpx.Timeout(timeout=timeout, connect=10.0)
    async with (
        httpx.AsyncClient(headers=headers, timeout=timeout_config) as http_client,
        streamable_http_client(server_url, http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(
            "ocr_image",
            {"image": image, "prompt": prompt, "mode": mode},
        )
    # 在 MCP 客户端上下文（anyio TaskGroup）外解析结果：
    # 块内抛出的异常会被 TaskGroup 聚合为晦涩的 ExceptionGroup，导致远端错误信息丢失。
    return parse_result(result)
