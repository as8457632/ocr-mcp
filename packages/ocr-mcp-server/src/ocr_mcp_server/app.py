"""构建 Streamable HTTP 的 ASGI 应用。"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Route


def create_app(server: Server) -> Starlette:
    """将 MCP Server 包装为挂载在 /mcp 的 Streamable HTTP 应用。"""
    session_manager = StreamableHTTPSessionManager(server)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route(
                "/mcp",
                endpoint=session_manager.asgi_app,
                methods=["GET", "POST", "DELETE"],
            )
        ],
    )
