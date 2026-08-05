"""服务端配置：从环境变量加载模型访问参数。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """配置缺失或非法时抛出。"""


def _parse_dotenv(path: str) -> None:
    """解析 .env 文件（KEY=value / export KEY=value，支持 # 注释与引号）并写入 os.environ。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _load_dotenv(filename: str = ".env") -> None:
    """从当前工作目录向上查找 .env 并加载，已存在的环境变量优先，不覆盖。"""
    current = os.getcwd()
    while True:
        candidate = os.path.join(current, filename)
        if os.path.isfile(candidate):
            _parse_dotenv(candidate)
            return
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


@dataclass(frozen=True)
class ServerConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    host: str = "0.0.0.0"
    port: int = 8000


def load_config(env: Mapping[str, str] | None = None) -> ServerConfig:
    """从环境变量构建服务端配置，缺失必填项时抛出 ConfigError。"""
    _load_dotenv()
    env = os.environ if env is None else env

    base_url = env.get("OCR_MCP_BASE_URL", "").strip()
    api_key = env.get("OCR_MCP_API_KEY", "").strip()
    model = env.get("OCR_MCP_MODEL", "").strip()

    missing = [
        name
        for name, value in (
            ("OCR_MCP_BASE_URL", base_url),
            ("OCR_MCP_API_KEY", api_key),
            ("OCR_MCP_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise ConfigError(f"缺少必需的环境变量: {', '.join(missing)}")

    try:
        timeout = float(env.get("OCR_MCP_TIMEOUT", "60"))
    except ValueError as exc:
        raise ConfigError("OCR_MCP_TIMEOUT 必须是数字（秒）") from exc
    if timeout <= 0:
        raise ConfigError("OCR_MCP_TIMEOUT 必须大于 0")

    try:
        port = int(env.get("OCR_MCP_PORT", "8000"))
    except ValueError as exc:
        raise ConfigError("OCR_MCP_PORT 必须是整数") from exc

    return ServerConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        host=env.get("OCR_MCP_HOST", "0.0.0.0"),
        port=port,
    )
