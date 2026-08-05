"""服务端入口：uv run ocr-mcp-server。"""

from __future__ import annotations

import sys

import uvicorn

from .app import create_app
from .config import ConfigError, load_config
from .server import create_server


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        sys.exit(1)
    app = create_app(create_server(config))
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
