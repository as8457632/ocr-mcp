import os
import socket
import threading
import time
from types import SimpleNamespace

import ocr_mcp_server.server as server_module
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from ocr_mcp_server.app import create_app
from ocr_mcp_server.config import ConfigError, ServerConfig, load_config
from ocr_mcp_server.ocr import (
    MODE_PLAIN,
    MODE_STRUCTURED,
    STRUCTURED_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_image_url,
    resolve_prompts,
    run_ocr,
)
from ocr_mcp_server.server import create_server

PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def _isolate_dotenv(tmp_path, monkeypatch):
    """隔离项目根 .env：将工作目录切到临时目录，避免影响配置加载测试。"""
    monkeypatch.chdir(tmp_path)
    for var in [v for v in os.environ if v.startswith("OCR_MCP_")]:
        del os.environ[var]
    yield
    for var in [v for v in os.environ if v.startswith("OCR_MCP_")]:
        del os.environ[var]


class FakeCompletions:
    def __init__(self, text: str):
        self._text = text
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._text))]
        )


class FakeChat:
    def __init__(self, text: str):
        self.completions = FakeCompletions(text)


class FakeAsyncOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = FakeChat("OCR 识别结果：你好，世界")


def test_load_config_full(monkeypatch):
    monkeypatch.setenv("OCR_MCP_BASE_URL", "http://model.example.com/v1")
    monkeypatch.setenv("OCR_MCP_API_KEY", "secret")
    monkeypatch.setenv("OCR_MCP_MODEL", "qwen-vl-max")
    monkeypatch.setenv("OCR_MCP_TIMEOUT", "30")
    monkeypatch.setenv("OCR_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("OCR_MCP_PORT", "9000")

    config = load_config()
    assert config.base_url == "http://model.example.com/v1"
    assert config.api_key == "secret"
    assert config.model == "qwen-vl-max"
    assert config.timeout == 30.0
    assert config.host == "127.0.0.1"
    assert config.port == 9000


def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("OCR_MCP_BASE_URL", "http://model.example.com/v1")
    monkeypatch.setenv("OCR_MCP_API_KEY", "secret")
    monkeypatch.setenv("OCR_MCP_MODEL", "qwen-vl-max")

    config = load_config()
    assert config.timeout == 60.0
    assert config.host == "0.0.0.0"
    assert config.port == 8000


def test_load_config_missing(monkeypatch):
    monkeypatch.delenv("OCR_MCP_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="OCR_MCP_API_KEY"):
        load_config({"OCR_MCP_BASE_URL": "http://x", "OCR_MCP_MODEL": "m"})


def test_load_config_invalid_port(monkeypatch):
    with pytest.raises(ConfigError, match="OCR_MCP_PORT"):
        load_config(
            {
                "OCR_MCP_BASE_URL": "http://x",
                "OCR_MCP_API_KEY": "k",
                "OCR_MCP_MODEL": "m",
                "OCR_MCP_PORT": "not-a-number",
            }
        )


def test_load_config_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text(
        "OCR_MCP_BASE_URL=https://dotenv.example/v1\n"
        "OCR_MCP_API_KEY=secret-key\n"
        "OCR_MCP_MODEL=dotenv-model\n"
        "OCR_MCP_PORT=9100\n",
        encoding="utf-8",
    )
    config = load_config()
    assert config.base_url == "https://dotenv.example/v1"
    assert config.api_key == "secret-key"
    assert config.model == "dotenv-model"
    assert config.port == 9100


def test_build_image_url():
    assert build_image_url(PNG_DATA_URI) == PNG_DATA_URI
    assert build_image_url("https://example.com/a.png") == "https://example.com/a.png"
    assert build_image_url("http://example.com/a.png") == "http://example.com/a.png"
    with pytest.raises(ValueError, match="data URI"):
        build_image_url("/tmp/a.png")


@pytest.mark.asyncio
async def test_run_ocr():
    fake = FakeAsyncOpenAI()
    client = fake
    text = await run_ocr(client, "test-model", PNG_DATA_URI, None)
    assert text == "OCR 识别结果：你好，世界"
    kwargs = fake.chat.completions.last_kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 0
    assert kwargs["messages"][0]["content"] == SYSTEM_PROMPT
    assert kwargs["messages"][1]["content"][0]["text"] == (
        "请识别图片中的全部文字，保持原有排版，直接输出识别结果，不要添加任何额外说明。"
    )


@pytest.mark.asyncio
async def test_run_ocr_structured():
    fake = FakeAsyncOpenAI()
    text = await run_ocr(fake, "test-model", PNG_DATA_URI, None, mode=MODE_STRUCTURED)
    assert text == "OCR 识别结果：你好，世界"
    kwargs = fake.chat.completions.last_kwargs
    assert kwargs["messages"][0]["content"] == STRUCTURED_SYSTEM_PROMPT
    assert "Markdown" in kwargs["messages"][1]["content"][0]["text"]


def test_resolve_prompts():
    system, user = resolve_prompts(MODE_PLAIN, None)
    assert system == SYSTEM_PROMPT
    assert "保持原有排版" in user

    system, user = resolve_prompts(MODE_STRUCTURED, None)
    assert system == STRUCTURED_SYSTEM_PROMPT
    assert "Markdown" in user

    system, user = resolve_prompts(MODE_PLAIN, "自定义 prompt")
    assert system == SYSTEM_PROMPT
    assert user == "自定义 prompt"

    with pytest.raises(ValueError, match="mode"):
        resolve_prompts("unknown", None)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("MCP server did not start")


def _start_server(monkeypatch, port: int):
    monkeypatch.setattr(server_module, "AsyncOpenAI", FakeAsyncOpenAI)
    config = ServerConfig(
        base_url="http://model.example.invalid/v1",
        api_key="test-key",
        model="test-model",
    )
    app = create_app(create_server(config))
    thread = threading.Thread(
        target=lambda: uvicorn.run(
            app, host="127.0.0.1", port=port, log_level="warning"
        ),
        daemon=True,
    )
    thread.start()
    _wait_for_server(port)
    return thread


@pytest.mark.asyncio
async def test_e2e_streamable_http(monkeypatch):

    port = _free_port()
    _start_server(monkeypatch, port)
    url = f"http://127.0.0.1:{port}/mcp"

    async with (
        streamable_http_client(url) as (read_stream, write_stream, _get_session_id),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        tools = await session.list_tools()
        assert any(tool.name == "ocr_image" for tool in tools.tools)

        result = await session.call_tool("ocr_image", {"image": PNG_DATA_URI})
        assert result.isError is False
        assert result.structuredContent["text"] == "OCR 识别结果：你好，世界"
        assert set(result.structuredContent) == {"text"}

        structured = await session.call_tool(
            "ocr_image", {"image": PNG_DATA_URI, "mode": MODE_STRUCTURED}
        )
        assert structured.isError is False
        assert structured.structuredContent["text"] == "OCR 识别结果：你好，世界"

        bad_mode = await session.call_tool(
            "ocr_image", {"image": PNG_DATA_URI, "mode": "unknown"}
        )
        assert bad_mode.isError is True
        assert "is not one of" in bad_mode.content[0].text

        bad = await session.call_tool("ocr_image", {"image": "/tmp/not-a-data-uri.png"})
        assert bad.isError is True
        assert "data URI" in bad.content[0].text
