"""客户端入口：uv run ocr-mcp-client（stdio MCP server）。"""

from __future__ import annotations

import asyncio
import sys

from mcp.server.stdio import stdio_server

from .config import ConfigError, load_config
from .server import create_server


async def async_main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        sys.exit(1)
    server = create_server(config)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
