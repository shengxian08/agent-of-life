"""
Agent Crew v5.1 — 统一 Agent，告别多 Agent 编排
"""
from __future__ import annotations

from typing import Any

from .unified_agent import get_unified_agent
from ..models.schemas import AgentRequest, AgentResponse


class HouseholdCrew:
    """Household management — single unified Agent"""

    def __init__(self):
        self.agent = get_unified_agent()

    async def chat(self, request: AgentRequest) -> AgentResponse:
        """直接调用统一 Agent"""
        return await self.agent.run(request)

    async def chat_stream(self, request: AgentRequest):
        """流式对话"""
        async for chunk in self.agent.run_stream(request):
            yield chunk

    async def run_workflow(
        self, workflow_type: str, user_id: str, session_id: str
    ) -> dict[str, Any]:
        """预定义工作流 — 统一 Agent 一句话搞定"""

        WORKFLOW_MESSAGES = {
            "daily_check": "生成今日概览，严格按三部分输出：1.警报汇总（过期食材、临期食材、逾期账单）；2.今日推荐一道优先消耗临期食材的菜谱；3.一条最紧急的维护提醒。每部分一句话，总字数不超过200字。",
            "weekly_plan": "帮我规划本周菜谱，优先消耗临期食材，然后生成对应的购物清单",
            "evening_routine": "预约今晚错峰运行：洗碗机→洗衣机→扫地机器人，计算省电金额",
            "smart_check": "深度全面检查：冰箱库存+家电维保+待缴账单+安防状态，如有临期食材推荐菜谱，给出完整行动建议",
            "security_check": "执行安防巡检：检查门禁、监控摄像头、门窗传感器状态",
        }

        msg = WORKFLOW_MESSAGES.get(workflow_type)
        if not msg:
            return {"error": f"Unknown workflow: {workflow_type}"}

        resp = await self.agent.run(AgentRequest(
            session_id=session_id,
            user_id=user_id,
            message=msg,
            intent=workflow_type,
        ))
        return {
            "workflow": workflow_type,
            "response": resp.response,
            "intent": resp.intent,
        }


_household_crew = None


def get_household_crew() -> HouseholdCrew:
    global _household_crew
    if _household_crew is None:
        from .base_agent import register_all_tools
        register_all_tools()
        _household_crew = HouseholdCrew()
    return _household_crew
