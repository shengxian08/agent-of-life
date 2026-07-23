"""
购物 Agent — LLM 驱动，自动管理冰箱库存、生成购物清单、比价
"""
from .base_agent import BaseAgent

SHOPPING_PROMPT = """你是专业的家庭购物管家。你的职责：

1. 冰箱管理：查看冰箱里有什么食材，哪些快过期了要赶紧吃，哪些快没了要补货
2. 购物清单：根据冰箱库存和用户的菜谱需求，智能生成采购清单
3. 比价推荐：对比盒马鲜生、永辉超市、美团买菜、叮咚买菜的价格，推荐最实惠的购买方案
4. 搜索商品：帮用户搜索特定商品在各超市的价格

回复要求：
- 用口语化的中文，像管家跟主人汇报一样自然
- 禁止使用 Markdown 格式（不要用 # | ** ` 等符号）
- 用 emoji 做视觉分隔，用自然换行分段
- 价格信息直接列出，比如"盒马 6.9元/500g，美团 4.9元/500g 最便宜"
- 每条信息之间空一行，清晰可读"""

class ShoppingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="shopping_agent",
            description="购物管家：冰箱库存、智能清单、商超比价",
            system_prompt=SHOPPING_PROMPT,
            tools=["get_fridge_inventory", "generate_shopping_list",
                   "compare_supermarket_prices", "add_to_shopping_list",
                   "search_product_prices",
                   "add_fridge_item", "remove_fridge_item", "record_shopping"],
        )