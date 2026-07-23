"""
统一家务管家 Agent v5.1 — 合并 6 个 Agent 为一个
所有工具注册到单一 Agent，由 LLM 自身判断调用哪个工具
"""
from .base_agent import BaseAgent
UNIFIED_PROMPT = """你是"家务AI管家"，全权负责家庭事务。

## 工具调用决策规则（严格按优先级执行）

### 第一层：前置判定（命中即执行，不自主思考）

如用户提到"之前、上次、历史、记得、记录、保存、哪天、什么时候"这类回顾性词汇 → 先调 search_knowledge_base 查家庭知识库。
如用户提到"现在、此刻、当前、实时、正在、看一下"这类即时性词汇 → 调实时工具（get_fridge_inventory、get_appliance_status 等），不搜知识库。
若同时命中（如"上次买的鸡蛋现在还能吃吗"）→ 先搜知识库找购买时间，再查冰箱确认当前状态。

### 第二层：未命中时自主判断

你有六方面能力和三类工具：

**实时工具**：get_fridge_inventory / get_appliance_status / check_maintenance_due / check_door_status / check_camera_feeds / get_security_events / track_packages / get_family_schedule / get_weekly_schedule 等

**知识库工具**：search_knowledge_base — BGE-M3 混合检索家庭长期记忆（菜谱做法、维保历史、采购记录、日程存档）

**无工具**：通用常识问题直接回答

## 回答规则
- 口语化中文，像管家汇报一样专业简洁
- 禁止 Markdown（不用 # | ** `），禁止使用面部表情 emoji（如 😊😂😄 等黄色圆脸表情）
- 允许使用功能性符号（如 ✅ ❌ 🔴 🟡 🟢 📅 💰 等），用空行分隔段落，可以使用表格对比修饰
- 知识库无结果 + 属于家庭私有数据 → 诚实说"暂未找到记录"，不编造
- 知识库无结果 + 属于通用常识 → 用自身知识回答，标注"未查到家庭存档"
- 实时工具无数据 → 如实告知，不猜测"""

class UnifiedAgent(BaseAgent):
    """统一管家：一个 Agent，全部工具"""

    def __init__(self):
        super().__init__(
            name="unified_household_agent",
            description="家务AI管家v5.1：购物/膳食/家电/维保/安防/事务，一个Agent全搞定",
            system_prompt=UNIFIED_PROMPT,
            tools=[
                # 购物工具
                "get_fridge_inventory",
                "generate_shopping_list",
                "compare_supermarket_prices",
                "search_product_prices",
                # 膳食工具
                "search_recipes",
                "get_recipe_detail",
                "generate_meal_plan",
                "match_recipes_by_ingredients",
                # 家电工具
                "get_appliance_status",
                "schedule_appliance",
                "generate_off_peak_schedule",
                "control_smart_appliance",
                # 维保工具
                "check_maintenance_due",
                "create_maintenance_task",
                "find_service_contact",
                "send_maintenance_reminder",
                "send_bill_reminder",
                # 安防工具
                "check_security_status",
                "arm_security_system",
                "disarm_security_system",
                "check_door_status",
                "view_camera_snapshot",
                # 家庭事务工具
                "check_schedule",
                "track_package",
                "add_household_task",
                "send_notification",
                # 知识库检索
                "search_knowledge_base",
                "web_search",
            ],
        )


_unified_agent = None

def get_unified_agent():
    global _unified_agent
    if _unified_agent is None:
        _unified_agent = UnifiedAgent()
    return _unified_agent
