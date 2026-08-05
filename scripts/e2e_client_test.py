"""通过 MCP stdio 协议调用 ocr-mcp-client，验证 客户端→服务端→mock模型 全链路。"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

CLIENT_BIN = "/home/wenzt/my_work/ocr-mcp/.venv/bin/ocr-mcp-client"
SERVER_URL = os.environ.get("OCR_MCP_SERVER_URL", "http://127.0.0.1:18000/mcp")


async def main() -> None:
    image = sys.argv[1] if len(sys.argv) > 1 else "/home/wenzt/my_work/yujian-project/bug-screenshot.png"
    params = StdioServerParameters(
        command=CLIENT_BIN,
        args=[],
        env={**os.environ, "OCR_MCP_SERVER_URL": SERVER_URL, "OCR_MCP_TIMEOUT": "30"},
    )
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        print("已发现工具:", [t.name for t in tools.tools])

        result = await session.call_tool("ocr_image", {"image": image})
        print("isError:", result.isError)
        print("返回内容:", result.structuredContent or result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
