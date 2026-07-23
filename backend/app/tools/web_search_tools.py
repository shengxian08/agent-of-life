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


# ================================================================
# 视频搜索 — Bilibili API（公开、免 Key、中文烹饪教程最全）
# ================================================================

def _fmt_count(n: int) -> str:
    """格式化播放量: 12345 → 1.2万"""
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


async def search_recipe_videos(query: str, max_results: int = 3) -> dict:
    """在 B 站搜索烹饪教学视频，返回视频卡片数据"""
    import urllib.parse
    keyword = urllib.parse.quote(query)
    url = (
        f"https://api.bilibili.com/x/web-interface/search/type"
        f"?search_type=video&keyword={keyword}&page=1"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
        "Cookie": "buvid3=agent-of-life",
    }

    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed", "videos": []}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return {"error": f"Bilibili API {resp.status_code}", "videos": []}
            data = resp.json()
    except Exception as e:
        logger.warning(f"Bilibili search failed: {e}")
        return {"error": str(e)[:200], "videos": []}

    results = data.get("data", {}).get("result", [])
    if not results:
        return {"message": "未找到相关视频", "videos": []}

    videos = []
    for v in results[:max_results]:
        title = (
            v.get("title", "")
            .replace('<em class="keyword">', "")
            .replace("</em>", "")
        )
        videos.append({
            "title": title,
            "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
            "thumbnail": v.get("pic", ""),
            "duration": v.get("duration", ""),
            "play_count": _fmt_count(v.get("play", 0)),
            "author": v.get("author", ""),
            "platform": "B站",
        })

    return {
        "platform": "B站",
        "query": query,
        "videos": videos,
    }
