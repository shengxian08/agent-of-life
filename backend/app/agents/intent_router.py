"""
意图路由器 v1.0 — 分层调度，减少 LLM 工具选择负担

策略：
1. 先用规则引擎快速匹配（零延迟，覆盖 80% 常见场景）
2. 未命中时用 LLM 一句话分类（极低延迟，max_tokens=20）
3. 根据意图域返回候选工具子集（5-10个，而非全部40+个）

效果：
- Prompt tokens 减少约 50%（工具 definitions 从 ~8000 tokens → ~2000 tokens）
- 工具选择准确率提升（LLM 在小集合里做选择比大集合更准确）
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from ..config import settings

# 六大领域 → 工具映射
DOMAIN_TOOLS: dict[str, list[str]] = {
    "shopping": [
        "get_fridge_inventory", "add_fridge_item", "remove_fridge_item",
        "record_shopping", "generate_shopping_list",
        "compare_supermarket_prices", "search_product_prices",
    ],
    "meal": [
        "search_recipes", "get_recipe_detail", "generate_meal_plan",
        "match_recipes_by_ingredients", "search_recipe_videos",
        "get_fridge_inventory",
    ],
    "appliance": [
        "get_appliance_status", "schedule_appliance",
        "generate_off_peak_schedule", "control_smart_appliance",
    ],
    "maintenance": [
        "check_maintenance_due", "create_maintenance_task",
        "find_service_contact", "send_maintenance_reminder",
        "send_bill_reminder",
    ],
    "security": [
        "check_door_status", "check_window_status",
        "check_camera_feeds", "get_security_events",
        "set_away_mode", "get_elderly_activity",
    ],
    "household": [
        "track_packages", "get_community_notices",
        "get_weekly_schedule", "find_free_time_slots",
        "schedule_task", "send_notification",
    ],
}

# 跨领域通用工具（任何意图都可能用到）
COMMON_TOOLS: list[str] = [
    "recall_user_memory",
    "search_knowledge_base",
    "web_search",
    "analyze_image",
]

# LLM 分类用的轻量 prompt
ROUTER_PROMPT = """你是意图路由器。分析用户消息，输出一个领域标签。

标签：shopping（购物/比价/冰箱库存）, meal（菜谱/膳食/做饭）, appliance（家电/错峰/省电）, maintenance（维保/维修/账单）, security（安防/门窗/老人）, household（日程/快递/社区）, general（寒暄/综合/其他）

规则：
- 只输出一个标签，不要解释
- "冰箱里有什么" → shopping
- "规划菜谱/今天吃什么" → meal
- "打开空调/错峰运行" → appliance
- "维修/账单/缴费" → maintenance
- "门窗/安防/监控" → security
- "快递/日程/通知" → household
- 寒暄/综合提问 → general"""


class IntentRouter:
    """意图路由器 — 规则优先 + LLM 兜底"""

    def __init__(self):
        self._client = None
        self._intent_cache: dict[str, str] = {}

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.openai_base_url,
                timeout=5.0,
                max_retries=1,
            )
        return self._client

    async def route(self, user_message: str) -> tuple[str, list[str]]:
        """分类用户意图，返回 (intent_label, candidate_tool_names)"""
        # 1. 规则快速匹配（零延迟）
        fast_intent = self._rule_match(user_message)
        if fast_intent:
            logger.debug(f"IntentRouter (rule): {fast_intent}")
            return fast_intent, self._get_tools(fast_intent)

        # 2. 缓存命中
        cache_key = user_message.strip()[:100].lower()
        if cache_key in self._intent_cache:
            cached = self._intent_cache[cache_key]
            logger.debug(f"IntentRouter (cache): {cached}")
            return cached, self._get_tools(cached)

        # 3. LLM 分类
        intent = await self._llm_classify(user_message)
        logger.debug(f"IntentRouter (LLM): {intent}")

        # 缓存（最多 200 条）
        if len(self._intent_cache) > 200:
            keys = list(self._intent_cache.keys())[:30]
            for k in keys:
                del self._intent_cache[k]
        self._intent_cache[cache_key] = intent

        return intent, self._get_tools(intent)

    def _get_tools(self, intent: str) -> list[str]:
        """根据意图返回候选工具列表"""
        if intent == "general":
            all_domain_tools = []
            for tools in DOMAIN_TOOLS.values():
                all_domain_tools.extend(tools)
            return list(dict.fromkeys(all_domain_tools + COMMON_TOOLS))

        domain_tools = DOMAIN_TOOLS.get(intent, [])
        result = domain_tools + COMMON_TOOLS
        return list(dict.fromkeys(result))

    def _rule_match(self, message: str) -> str | None:
        """规则快速匹配（零延迟，覆盖 80% 场景）"""
        msg = message.strip()

        # 寒暄/简短（返回 general 而非 None，因为 LLM 分类太慢）
        short_greetings = {"你好", "hi", "hello", "在吗", "早", "晚安", "谢谢", "你是谁",
                           "你能做什么", "帮助", "help"}
        if msg.lower() in short_greetings or len(msg) < 3:
            return "general"

        # 购物关键词
        if any(kw in msg for kw in ["冰箱", "买了", "加入冰箱", "购物清单", "比价",
                                      "盒马", "永辉", "快递", "包裹", "库存"]):
            return "shopping"

        # 菜谱关键词
        if any(kw in msg for kw in ["怎么做", "菜谱", "食谱", "做法", "今天吃什么",
                                      "晚餐", "午餐", "早餐", "做饭", "烹饪",
                                      "红烧", "清蒸", "炖", "视频"]):
            if "维修" not in msg and "检查" not in msg:
                return "meal"

        # 家电关键词
        if any(kw in msg for kw in ["空调", "洗衣机", "洗碗机", "扫地", "错峰",
                                      "省电", "预约", "家电状态"]):
            return "appliance"

        # 维保关键词
        if any(kw in msg for kw in ["维修", "保养", "坏了", "故障", "账单", "缴费",
                                      "师傅", "售后", "到期"]):
            return "maintenance"

        # 安防关键词
        if any(kw in msg for kw in ["安防", "门窗", "监控", "摄像头", "门锁", "布防",
                                      "离家", "老人活动"]):
            return "security"

        # 家庭事务关键词
        if any(kw in msg for kw in ["日程", "快递单号", "社区", "空闲", "安排", "提醒"]):
            return "household"

        # 综合/巡检 → general
        if any(kw in msg for kw in ["巡检", "概览", "全面", "综合"]):
            return "general"

        return None

    async def _llm_classify(self, user_message: str) -> str:
        """LLM 分类（轻量调用，max_tokens=20，延迟 < 500ms）"""
        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": ROUTER_PROMPT},
                    {"role": "user", "content": user_message[:300]},
                ],
                temperature=0,
                max_tokens=20,
            )
            label = (resp.choices[0].message.content or "general").strip().lower()
            label = label.split("\n")[0].strip().rstrip(".,，。")
            valid_labels = set(DOMAIN_TOOLS.keys()) | {"general"}
            if label not in valid_labels:
                for valid in valid_labels:
                    if valid in label or label in valid:
                        return valid
                return "general"
            return label
        except Exception as e:
            logger.debug(f"IntentRouter LLM classify failed: {e}")
            return "general"


_router: IntentRouter | None = None


def get_intent_router() -> IntentRouter:
    global _router
    if _router is None:
        _router = IntentRouter()
    return _router
