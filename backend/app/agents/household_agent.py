"""
家庭事务 Agent v5.0 — 日程管理、快递追踪、物业对接、访客预约
"""
from .base_agent import BaseAgent

HOUSEHOLD_PROMPT = """你是家庭事务管家。你的职责：

1. 日程管理：查看和管理家庭成员日程，冲突提醒
2. 快递追踪：查询在途快递状态，到件提醒
3. 物业对接：预约维修、缴纳物业费、查看社区通知
4. 访客预约：管理访客登记、临时门禁授权

回复要求：
- 口语化中文，像私人助理一样自然
- 禁止 Markdown 格式
- 用 emoji 做视觉分隔
- 涉及时间的务必明确日期和时间点"""

class HouseholdAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="household_agent",
            description="家庭事务Agent：日程管理、快递追踪、物业对接、访客预约",
            system_prompt=HOUSEHOLD_PROMPT,
            tools=[
                "get_weekly_schedule", "add_calendar_event",
                "find_free_time_slots", "schedule_task",
                "track_packages", "get_community_notices",
                "send_notification",
            ],
        )

