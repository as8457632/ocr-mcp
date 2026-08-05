import base64
import contextlib
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import CallToolResult, TextContent, Tool
from ocr_mcp_client.config import ConfigError, load_config
from ocr_mcp_client.remote import call_remote_ocr, parse_result
from ocr_mcp_client.server import file_to_data_uri, to_server_image
from starlette.applications import Starlette
from starlette.routing import Route

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_DATA_URI = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")


@pytest.fixture(autouse=True)
def _isolate_dotenv(tmp_path, monkeypatch):
    """隔离项目根 .env：将工作目录切到临时目录，避免影响配置加载测试。"""
    monkeypatch.chdir(tmp_path)
    for var in [v for v in os.environ if v.startswith("OCR_MCP_")]:
        del os.environ[var]
    yield
    for var in [v for v in os.environ if v.startswith("OCR_MCP_")]:
        del os.environ[var]


def make_fake_remote_server() -> Server:
    server = Server("fake-remote-ocr")
    received_arguments: list[dict] = []

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="ocr_image",
                description="fake remote OCR",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "image": {"type": "string"},
                        "prompt": {"type": ["string", "null"]},
                        "mode": {"type": "string", "enum": ["plain", "structured"]},
                    },
                    "required": ["image"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> dict:
        if name != "ocr_image":
            raise ValueError(f"未知工具: {name}")
        received_arguments.append(arguments)
        if not isinstance(arguments.get("image"), str) or not arguments[
            "image"
        ].startswith("data:"):
            raise ValueError("image 必须是 data URI")
        return {"text": "FAKE OCR TEXT", "model": "fake-model"}

    return server, received_arguments


def make_fake_remote_app(server: Server) -> Starlette:
    manager = StreamableHTTPSessionManager(server)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with manager.run():
            yield

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/mcp", endpoint=manager.asgi_app, methods=["GET", "POST", "DELETE"])
        ],
    )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("remote MCP server did not start")


def start_fake_remote() -> tuple[str, list[dict]]:
    port = free_port()
    server, received = make_fake_remote_server()
    app = make_fake_remote_app(server)
    thread = threading.Thread(
        target=lambda: uvicorn.run(
            app, host="127.0.0.1", port=port, log_level="warning"
        ),
        daemon=True,
    )
    thread.start()
    wait_for_server(port)
    return f"http://127.0.0.1:{port}/mcp", received


def test_load_config(monkeypatch):
    monkeypatch.setenv("OCR_MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
    monkeypatch.setenv("OCR_MCP_SERVER_TOKEN", "abc")
    monkeypatch.setenv("OCR_MCP_TIMEOUT", "45")

    config = load_config()
    assert config.server_url == "http://127.0.0.1:8000/mcp"
    assert config.server_token == "abc"
    assert config.timeout == 45.0


def test_load_config_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text(
        "OCR_MCP_SERVER_URL=https://dotenv.example/mcp\nOCR_MCP_TIMEOUT=30\n",
        encoding="utf-8",
    )
    config = load_config()
    assert config.server_url == "https://dotenv.example/mcp"
    assert config.timeout == 30.0


def test_load_config_missing():
    with pytest.raises(ConfigError, match="OCR_MCP_SERVER_URL"):
        load_config({})


def test_load_config_bad_url():
    with pytest.raises(ConfigError, match="http"):
        load_config({"OCR_MCP_SERVER_URL": "localhost:8000"})


def test_file_to_data_uri(tmp_path: Path):
    image = tmp_path / "a.png"
    image.write_bytes(PNG_BYTES)

    uri = file_to_data_uri(str(image))
    assert uri.startswith("data:image/png;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == PNG_BYTES


def test_file_to_data_uri_missing(tmp_path: Path):
    with pytest.raises(ValueError, match="不存在"):
        file_to_data_uri(str(tmp_path / "nope.png"))


def test_file_to_data_uri_unsupported(tmp_path: Path):
    image = tmp_path / "a.pdf"
    image.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError, match="不支持的图片格式"):
        file_to_data_uri(str(image))


def test_file_to_data_uri_empty(tmp_path: Path):
    image = tmp_path / "empty.png"
    image.write_bytes(b"")
    with pytest.raises(ValueError, match="为空"):
        file_to_data_uri(str(image))


def test_to_server_image(tmp_path: Path):
    assert to_server_image("https://example.com/a.png") == "https://example.com/a.png"
    image = tmp_path / "a.png"
    image.write_bytes(PNG_BYTES)
    assert to_server_image(str(image)).startswith("data:image/png;base64,")


def _text_result(
    text: str, *, is_error: bool = False, structured: dict | None = None
) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=structured,
        isError=is_error,
    )


def test_parse_result_structured():
    result = _text_result(
        '{"text": "x", "model": "m"}',
        structured={"text": "结构化文本", "model": "qwen-vl"},
    )
    parsed = parse_result(result)
    assert parsed == {"text": "结构化文本", "model": "qwen-vl"}


def test_parse_result_json_fallback():
    result = _text_result('{"text": "JSON 文本", "model": "glm-4v"}')
    parsed = parse_result(result)
    assert parsed == {"text": "JSON 文本", "model": "glm-4v"}


def test_parse_result_plain_text():
    result = _text_result("纯文本结果")
    parsed = parse_result(result)
    assert parsed == {"text": "纯文本结果", "model": "unknown"}


def test_parse_result_error():
    result = _text_result("远端错误", is_error=True)
    with pytest.raises(RuntimeError, match="远端错误"):
        parse_result(result)


@pytest.mark.asyncio
async def test_call_remote_ocr_e2e():
    url, received = start_fake_remote()
    result = await call_remote_ocr(
        url, PNG_DATA_URI, prompt="识别", mode="structured", token=None, timeout=30
    )
    assert result == {"text": "FAKE OCR TEXT", "model": "fake-model"}
    assert received[-1]["mode"] == "structured"
    assert received[-1]["prompt"] == "识别"


@pytest.mark.asyncio
async def test_full_chain_stdio(tmp_path: Path):
    url, received = start_fake_remote()
    image = tmp_path / "a.png"
    image.write_bytes(PNG_BYTES)

    env = {
        **os.environ,
        "OCR_MCP_SERVER_URL": url,
        "OCR_MCP_TIMEOUT": "30",
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ocr_mcp_client"],
        env=env,
    )
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        tools = await session.list_tools()
        assert any(tool.name == "ocr_image" for tool in tools.tools)

        result = await session.call_tool("ocr_image", {"image": str(image)})
        assert result.isError is False
        assert result.structuredContent["text"] == "FAKE OCR TEXT"
        assert result.structuredContent["model"] == "fake-model"
        assert result.structuredContent["source"] == str(image)

        structured = await session.call_tool(
            "ocr_image", {"image": str(image), "mode": "structured"}
        )
        assert structured.isError is False
        assert structured.structuredContent["text"] == "FAKE OCR TEXT"
        assert received[-1]["mode"] == "structured"
