"""客户端配置：从环境变量加载服务端地址。"""

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
class ClientConfig:
    server_url: str
    server_token: str | None = None
    timeout: float = 60.0


def load_config(env: Mapping[str, str] | None = None) -> ClientConfig:
    """从环境变量构建客户端配置，缺失必填项时抛出 ConfigError。"""
    _load_dotenv()
    env = os.environ if env is None else env

    server_url = env.get("OCR_MCP_SERVER_URL", "").strip()
    if not server_url:
        raise ConfigError("缺少必需的环境变量: OCR_MCP_SERVER_URL")
    if not server_url.startswith(("http://", "https://")):
        raise ConfigError("OCR_MCP_SERVER_URL 必须是 http(s):// 地址")

    try:
        timeout = float(env.get("OCR_MCP_TIMEOUT", "60"))
    except ValueError as exc:
        raise ConfigError("OCR_MCP_TIMEOUT 必须是数字（秒）") from exc
    if timeout <= 0:
        raise ConfigError("OCR_MCP_TIMEOUT 必须大于 0")

    token = env.get("OCR_MCP_SERVER_TOKEN", "").strip()
    return ClientConfig(
        server_url=server_url,
        server_token=token or None,
        timeout=timeout,
    )
