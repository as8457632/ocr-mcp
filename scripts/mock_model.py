"""Mock 多模态模型服务：模拟 OpenAI 兼容的 /v1/chat/completions 接口。

用于在未提供真实模型 API 前做端到端联调。启动后监听 127.0.0.1:18080。
"""

from __future__ import annotations

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


async def chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    model = body.get("model", "unknown")

    prompt_text = ""
    image_desc = "none"
    for msg in reversed(body.get("messages", [])):
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    image_desc = "data-uri" if url.startswith("data:") else url
                elif part.get("type") == "text":
                    prompt_text = part.get("text", "")
        elif isinstance(content, str):
            prompt_text = content
        if image_desc != "none" or prompt_text:
            break

    text = f"MOCK-OCR[{model}] image={image_desc} prompt={prompt_text or '(默认OCR提示)'}"
    return JSONResponse(
        {
            "id": "chatcmpl-mock-001",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )


app = Starlette(routes=[Route("/v1/chat/completions", chat_completions, methods=["POST"])])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18080, log_level="info")
