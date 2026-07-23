"""
外部搜索工具 — 知识库兜底的第三层
支持：DuckDuckGo (免费) / 搜索引擎 API (可选)
"""
from __future__ import annotations

from loguru import logger

try:
    from duckduckgo_search import DDGS
    _DDGS_AVAILABLE = True
except ImportError:
    _DDGS_AVAILABLE = False


async def web_search(query: str, max_results: int = 5) -> dict:
    """搜索互联网获取信息（知识库兜底）

    优先使用 DuckDuckGo（免费无需 API Key）。
    如果 pip install duckduckgo_search 未安装，返回提示。
    """
    if not _DDGS_AVAILABLE:
        return {
            "fallback": True,
            "source": "none",
            "message": (
                "外部搜索不可用。如需启用请运行 pip install duckduckgo_search。"
                "你可以根据你的知识直接回答用户的问题。"
            ),
            "results": [],
        }

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return {
            "fallback": True,
            "source": "error",
            "message": f"外部搜索失败 ({str(e)[:100]})。请根据你的知识回答用户问题。",
            "results": [],
        }

    if not results:
        return {
            "fallback": True,
            "source": "duckduckgo",
            "message": "外部搜索未找到相关内容。请根据你的知识回答用户问题。",
            "results": [],
        }

    return {
        "fallback": False,
        "source": "duckduckgo",
        "message": f"从互联网找到 {len(results)} 条相关信息",
        "results": [
            {
                "title": r.get("title", ""),
                "body": r.get("body", "")[:300],
                "href": r.get("href", ""),
            }
            for r in results[:max_results]
        ],
    }
