"""
购物路由
"""
from fastapi import APIRouter, Depends, Query

from ...agents.shopping_agent import ShoppingAgent
from ...tools.shopping_tools import (
    get_fridge_inventory, compare_supermarket_prices,
    generate_shopping_list, search_product_prices,
)
from ..deps import get_crew

router = APIRouter(prefix="/shopping", tags=["Shopping"])


@router.get("/fridge/{user_id}")
async def fridge_inventory(user_id: str):
    """获取冰箱库存"""
    items = await get_fridge_inventory(user_id)
    return {"user_id": user_id, "items": items, "count": len(items)}


@router.get("/compare")
async def compare_prices(
    item_name: str = Query(..., description="商品名称"),
    supermarkets: str = Query("", description="超市名称，逗号分隔"),
):
    """比价"""
    sm_list = [s.strip() for s in supermarkets.split(",") if s.strip()] if supermarkets else None
    results = await compare_supermarket_prices(item_name, sm_list)
    return {"item": item_name, "comparisons": [r.model_dump() for r in results]}


@router.post("/list/{user_id}")
async def create_shopping_list(user_id: str):
    """生成购物清单"""
    result = await generate_shopping_list(user_id)
    return result.model_dump()


@router.get("/search")
async def search_prices(
    query: str = Query(..., description="搜索关键词"),
    city: str = Query("北京"),
):
    """搜索商品价格"""
    results = await search_product_prices(query, city)
    return {"query": query, "results": [r.model_dump() for r in results]}
