"""
超市价格爬虫 v4.0 — Playwright 真实爬取 + 价格数据库降级
策略：优先实时爬取 → 失败降级到本地价格数据库
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


SUPERMARKET_CONFIGS = {
    "盒马鲜生": {
        "search_url": "https://www.freshhema.com/search?q={query}",
        "selectors": {
            "product_card": ".product-item, .sku-item, [class*='product']",
            "name": ".product-name, .sku-name, [class*='name']",
            "price": ".product-price, .price, [class*='price']",
        },
        "timeout_ms": 15000,
    },
    "永辉超市": {
        "search_url": "https://www.yonghui.com.cn/search?keyword={query}",
        "selectors": {
            "product_card": ".goods-item, [class*='goods']",
            "name": ".goods-name, [class*='name']",
            "price": ".goods-price, [class*='price']",
        },
        "timeout_ms": 15000,
    },
    "美团买菜": {
        "search_url": "https://i.meituan.com/s/{query}",
        "selectors": {
            "product_card": ".food-item, [class*='item']",
            "name": ".food-name, [class*='title']",
            "price": ".food-price, [class*='price']",
        },
        "timeout_ms": 10000,
    },
}


async def crawl_prices(
    product_name: str,
    supermarket: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """爬取指定超市的商品价格 — 真实请求 + 智能降级

    Returns:
        [{"name": str, "price": float, "unit": str, "supermarket": str, "source": str}, ...]
    """
    config = SUPERMARKET_CONFIGS.get(supermarket)
    if not config:
        logger.warning(f"No crawler config for {supermarket}")
        return []

    results = []

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            try:
                search_url = config["search_url"].format(query=product_name)
                await page.goto(search_url, wait_until="domcontentloaded", timeout=config["timeout_ms"])

                # 等待商品加载
                await asyncio.sleep(2)

                selectors = config["selectors"]
                product_cards = await page.query_selector_all(selectors["product_card"])

                for card in product_cards[:max_results]:
                    try:
                        name_el = await card.query_selector(selectors["name"])
                        price_el = await card.query_selector(selectors["price"])

                        if name_el and price_el:
                            name_text = (await name_el.inner_text()).strip()
                            price_text = (await price_el.inner_text()).strip()

                            # 提取价格数字
                            import re
                            price_match = re.search(r"[\d.]+", price_text)
                            price = float(price_match.group()) if price_match else 0.0

                            # 提取单位
                            unit_match = re.search(r"[元￥¥]?\s*/\s*(\S+)", price_text)
                            unit = unit_match.group(1) if unit_match else "份"

                            if price > 0 and name_text:
                                results.append({
                                    "name": name_text,
                                    "price": price,
                                    "unit": unit,
                                    "supermarket": supermarket,
                                    "source": "实时爬取",
                                })
                    except Exception:
                        continue

            except Exception as e:
                logger.warning(f"Page load/timeout for {supermarket}: {e}")
            finally:
                await browser.close()

    except ImportError:
        logger.debug("Playwright not installed, using price database fallback")
    except Exception as e:
        logger.warning(f"Crawler error for {supermarket}: {e}")

    # 降级：使用本地价格数据库
    if not results:
        results = await _fallback_price_lookup(product_name, supermarket)

    return results


async def _fallback_price_lookup(
    product_name: str, supermarket: str
) -> list[dict[str, Any]]:
    """价格数据库降级查询"""
    from ..tools.shopping_tools import compare_supermarket_prices
    try:
        comparisons = await compare_supermarket_prices(
            product_name, supermarkets=[supermarket]
        )
        return [
            {
                "name": c.item_name,
                "price": c.price,
                "unit": c.unit,
                "supermarket": c.supermarket,
                "source": "价格数据库",
            }
            for c in comparisons
        ]
    except Exception:
        return []


async def crawl_hema_prices(product_name: str) -> list[dict[str, Any]]:
    """爬取盒马鲜生价格 (兼容旧接口)"""
    return await crawl_prices(product_name, "盒马鲜生")


async def crawl_meituan_prices(product_name: str) -> list[dict[str, Any]]:
    """爬取美团买菜价格 (兼容旧接口)"""
    return await crawl_prices(product_name, "美团买菜")


async def crawl_all_supermarkets(
    product_name: str,
    supermarkets: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """并行爬取所有超市价格"""
    if supermarkets is None:
        supermarkets = list(SUPERMARKET_CONFIGS.keys())

    tasks = {
        sm: crawl_prices(product_name, sm)
        for sm in supermarkets
    }
    results = {}
    for sm, task in tasks.items():
        try:
            results[sm] = await task
        except Exception as e:
            logger.warning(f"Failed to crawl {sm}: {e}")
            results[sm] = []

    return results
