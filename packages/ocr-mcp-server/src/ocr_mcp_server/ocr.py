"""OCR 识别核心：调用多模态模型提取图片文字。"""

from __future__ import annotations

from openai import AsyncOpenAI

MODE_PLAIN = "plain"
MODE_STRUCTURED = "structured"
SUPPORTED_MODES = (MODE_PLAIN, MODE_STRUCTURED)

DEFAULT_OCR_PROMPT = (
    "请识别图片中的全部文字，保持原有排版，直接输出识别结果，不要添加任何额外说明。"
)

STRUCTURED_OCR_PROMPT = (
    "请识别图片中的全部文字，按视觉布局组织输出：标题用 Markdown 标题（#），"
    "菜单与列表用无序列表，表格数据用 Markdown 表格，数值与标签保持对应关系。"
    "不要添加任何解释。"
)

SYSTEM_PROMPT = "You are an OCR engine. Extract all text from images accurately and faithfully, preserving the original layout."

STRUCTURED_SYSTEM_PROMPT = (
    "You are an OCR engine specialized in documents and software UI screenshots. "
    "Extract all meaningful text exactly as shown, organized by visual layout. "
    "Ignore decorative or duplicated elements. "
    "Use Markdown structure to reflect hierarchy: headings, bullet lists, tables. "
    "Output only the extracted content."
)


def resolve_prompts(mode: str, prompt: str | None) -> tuple[str, str]:
    """根据识别模式与自定义 prompt 解析 (system_prompt, user_prompt)。"""
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"mode 必须是 {' 或 '.join(SUPPORTED_MODES)} 之一")
    if mode == MODE_STRUCTURED:
        system_prompt, default_user_prompt = (
            STRUCTURED_SYSTEM_PROMPT,
            STRUCTURED_OCR_PROMPT,
        )
    else:
        system_prompt, default_user_prompt = SYSTEM_PROMPT, DEFAULT_OCR_PROMPT
    return system_prompt, prompt or default_user_prompt


def build_image_url(image: str) -> str:
    """校验并返回可直接发给多模态模型的图片地址（data URI 或 http(s) URL）。"""
    if image.startswith("data:") and ";base64," in image:
        return image
    if image.startswith(("http://", "https://")):
        return image
    raise ValueError(
        "image 必须是 data URI（data:image/...;base64,...）或 http(s):// URL"
    )


async def run_ocr(
    client: AsyncOpenAI,
    model: str,
    image: str,
    prompt: str | None = None,
    mode: str = MODE_PLAIN,
) -> str:
    """调用多模态模型识别图片中的文字，返回识别文本。"""
    image_url = build_image_url(image)
    system_prompt, user_prompt = resolve_prompts(mode, prompt)
    response = await client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ],
    )
    content = response.choices[0].message.content
    return content or ""
