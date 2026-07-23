"""
购物业务服务层
"""
from __future__ import annotations

from typing import Any

from ..tools.shopping_tools import (
    get_fridge_inventory, generate_shopping_list,
    compare_supermarket_prices, search_product_prices,
)
from ..models.schemas import ShoppingList


class ShoppingService:
    """购物业务服务"""

    @staticmethod
    async def get_fridge(user_id: str) -> list[dict[str, Any]]:
        return await get_fridge_inventory(user_id)

    @staticmethod
    async def create_list(user_id: str, meal_plan: dict = None) -> ShoppingList:
        return await generate_shopping_list(user_id, meal_plan=meal_plan)

    @staticmethod
    async def compare(item_name: str, supermarkets: list[str] = None):
        return await compare_supermarket_prices(item_name, supermarkets)

    @staticmethod
    async def search(query: str, city: str = "北京"):
        return await search_product_prices(query, city)
