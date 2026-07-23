"""
菜谱规划路由
"""
from fastapi import APIRouter, Depends, Query

from ...tools.recipe_tools import (
    search_recipes, get_recipe_detail,
    generate_meal_plan, match_recipes_by_ingredients,
)
from ...tools.shopping_tools import get_fridge_inventory

router = APIRouter(prefix="/meal-plan", tags=["Meal Plan"])


@router.get("/plan/{user_id}")
async def create_meal_plan(
    user_id: str,
    days: int = Query(7, ge=1, le=14),
    start_date: str = "",
):
    """生成一周菜谱"""
    fridge = await get_fridge_inventory(user_id)
    from datetime import date
    sd = date.fromisoformat(start_date) if start_date else None
    plan = await generate_meal_plan(user_id, fridge, start_date=sd, days=days)
    return plan.model_dump()


@router.get("/match/{user_id}")
async def match_ingredients(
    user_id: str,
    meal_type: str = "",
    limit: int = Query(5, ge=1, le=20),
):
    """根据冰箱食材匹配菜谱"""
    fridge = await get_fridge_inventory(user_id)
    names = [item["name"] for item in fridge]
    matches = await match_recipes_by_ingredients(names, meal_type, limit)
    return {"ingredients_available": names, "matches": matches}


@router.get("/search")
async def search_recipe(
    query: str = "",
    meal_type: str = "",
    cuisine: str = "",
    max_time: int = Query(0, alias="max_cooking_time"),
    limit: int = Query(10),
):
    """搜索菜谱"""
    results = await search_recipes(query, meal_type, cuisine, max_time, limit=limit)
    return {"results": [r.model_dump() for r in results]}


@router.get("/recipe/{recipe_id}")
async def recipe_detail(recipe_id: str):
    """菜谱详情"""
    recipe = await get_recipe_detail(recipe_id)
    if recipe:
        return recipe.model_dump()
    return {"error": "Recipe not found"}
