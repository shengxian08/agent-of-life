"""
统一家务管家 Agent v5.5 — 合并 6 个 Agent 为一个
所有工具注册到单一 Agent，由 LLM 自身判断调用哪个工具
新增：长期记忆检索 (recall_user_memory) + 跨会话记忆感知 + 自动偏好学习
"""
from .base_agent import BaseAgent
UNIFIED_PROMPT = """你是"家务AI管家"，全权负责家庭事务。调用工具时优先并行获取数据再回答。

## 行为准则
- 简单寒暄 → 简短介绍自己即可，不要运行巡检或输出报告类内容
- 用户提及食材信息（"买了/家里有/还剩X斤"等）→ 直接调 add_fridge_item 入库，自动推断单位和保质期，回复中简短确认。不要反问"需要我记录吗"
- 问菜谱做法 → 同时调 search_recipes + search_recipe_videos，文字步骤只输出一次
- 问题涉及历史/偏好/过往记录 → 同时调 recall_user_memory + search_knowledge_base
- 新用户（检查后发现冰箱和家电都空）→ 简短介绍你能做什么，然后逐步了解家庭成员、口味偏好、过敏物、忌口、预算。不要一次性全问

## 输出规范
- 口语化中文，Markdown 层级排板：## 标题、**加粗**、1. 步骤编号、- 列表，用空行分隔段落
- 禁止面部 emoji（😊😂😄），允许功能符号（✅❌🔴🟡🟢📅💰）
- 回复中不出现"视频"二字，不输出视频名称、作者、时长、播放量、链接
- 获取到用户长期记忆时自然提及，体现熟悉感
- 知识库和记忆均无结果 → "暂未找到记录"，不编造
- 知识库无结果但属通用常识 → 可答，标注"未查到家庭存档"
- 实时工具无数据 → 如实告知，不猜测"""

class UnifiedAgent(BaseAgent):
    """统一管家：一个 Agent，全部工具"""

    def __init__(self):
        super().__init__(
            name="unified_household_agent",
            description="家务AI管家v5.5：购物/膳食/家电/维保/安防/事务/记忆，一个Agent全搞定",
            system_prompt=UNIFIED_PROMPT,
            tools=[
                # 记忆工具（新增）
                "recall_user_memory",
                # 购物工具
                "get_fridge_inventory",
                "add_fridge_item",
                "remove_fridge_item",
                "record_shopping",
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
                "check_door_status",
                "check_window_status",
                "check_camera_feeds",
                "get_security_events",
                "set_away_mode",
                "get_elderly_activity",
                # 家庭事务工具
                "track_packages",
                "get_community_notices",
                "get_weekly_schedule",
                "find_free_time_slots",
                "schedule_task",
                "send_notification",
                # 知识库检索
                "search_knowledge_base",
                "web_search",
                # 视频搜索
                "search_recipe_videos",
                # 视觉识别
                "analyze_image",
            ],
        )


_unified_agent = None

def get_unified_agent():
    global _unified_agent
    if _unified_agent is None:
        _unified_agent = UnifiedAgent()
    return _unified_agent
