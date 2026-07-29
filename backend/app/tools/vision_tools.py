"""
视觉识别工具 — 拍照识食材、图片分析
"""
import base64
from loguru import logger


async def analyze_image(image_base64: str, prompt: str = "") -> dict:
    """用视觉 LLM 分析图片内容，返回文字描述

    Args:
        image_base64: 图片的 base64 编码（不含 data:image 前缀）
        prompt: 额外提示，如"识别冰箱里的食材"

    Returns:
        {"description": "图片中的内容描述", "items": ["鸡蛋","番茄"...]}
    """
    from app.config import settings

    api_key = settings.vision_api_key or settings.api_key
    base_url = settings.vision_base_url or settings.openai_base_url
    model = settings.vision_model

    if not settings.vision_enabled:
        return {"error": "视觉功能未启用，请设置 VISION_ENABLED=true 和视觉模型"}

    if not api_key or api_key == "sk-xxx":
        return {"error": "未配置视觉模型 API Key"}

    user_prompt = prompt or "请描述这张图片里有什么。如果是冰箱内部，请列出每种食材的名称、数量和大概新鲜程度。"

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)

        resp = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "low",
                        }
                    }
                ]
            }],
            max_tokens=500,
        )

        description = resp.choices[0].message.content or ""
        logger.info(f"Vision analysis: {description[:100]}...")

        return {
            "description": description,
            "raw": description,
        }

    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return {"error": f"图片分析失败: {str(e)[:200]}"}
