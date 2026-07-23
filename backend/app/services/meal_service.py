"""
菜谱业务服务层
"""
from __future__ import annotations

from ..tools.recipe_tools import (
    search_recipes, get_recipe_detail,
    generate_meal_plan, match_recipes_by_ingredients,
)
from ..tools.shopping_tools import get_fridge_inventory
from ..models.schemas import MealPlan


class MealService:
    """菜谱业务服务"""

    @staticmethod
    async def plan_week(user_id: str, days: int = 7) -> MealPlan:
        fridge = await get_fridge_inventory(user_id)
        return await generate_meal_plan(user_id, fridge, days=days)

    @staticmethod
    async def match(user_id: str, meal_type: str = ""):
        fridge = await get_fridge_inventory(user_id)
        names = [item["name"] for item in fridge]
        return await match_recipes_by_ingredients(names, meal_type)

    @staticmethod
    async def search(query: str = "", **filters):
        return await search_recipes(query=query, **filters)

    @staticmethod
    async def detail(recipe_id: str):
        return await get_recipe_detail(recipe_id)
