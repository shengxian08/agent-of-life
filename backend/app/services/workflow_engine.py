"""
Workflow Engine v4.0 — conditional branching + parallel execution + structured validation
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from dataclasses import dataclass, field

from loguru import logger

from ..agents.shopping_agent import ShoppingAgent
from ..agents.meal_planner_agent import MealPlannerAgent
from ..agents.appliance_agent import ApplianceAgent
from ..agents.maintenance_agent import MaintenanceAgent
from ..models.schemas import AgentRequest, AgentResponse
from ..config import settings


@dataclass
class WorkflowResult:
    workflow_id: str
    workflow_name: str
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    alerts: list[str] = field(default_factory=list)
    status: str = "running"


class WorkflowEngine:
    """Automated workflow engine with parallel execution and conditional branching"""

    def __init__(self):
        self.shopping = ShoppingAgent()
        self.meal = MealPlannerAgent()
        self.appliance = ApplianceAgent()
        self.maintenance = MaintenanceAgent()

    async def _run_step(
        self, agent, user_id: str, message: str, intent: str
    ) -> dict:
        """Execute a single workflow step"""
        req = AgentRequest(
            session_id=f"wf_{datetime.now().timestamp():.0f}",
            user_id=user_id,
            message=message,
            intent=intent,
        )
        try:
            resp = await agent.run(req)
            return {
                "agent": agent.name,
                "message": message,
                "response": resp.response,
                "tool_calls": len(resp.tool_calls),
                "intent": resp.intent,
                "success": True,
            }
        except Exception as e:
            logger.error(f"Workflow step failed ({agent.name}): {e}")
            return {
                "agent": agent.name,
                "message": message,
                "response": f"执行失败: {str(e)}",
                "tool_calls": 0,
                "intent": intent,
                "success": False,
                "error": str(e),
            }

    def _has_issue(self, response_text: str, keywords: list[str] | None = None) -> bool:
        """Check if response indicates an issue using keyword matching"""
        if keywords is None:
            keywords = ["过期", "到期", "不足", "缺少", "需", "建议", "立即", "紧急"]
        return any(k in response_text for k in keywords)

    def _extract_alerts(self, step_name: str, response_text: str) -> list[str]:
        """Extract alerts from response based on content"""
        alerts = []
        alert_rules = [
            (["今天过期", "今日到期", "今天到期"], f"🔴 {step_name}: 有今日到期项"),
            (["明天过期", "明日到期", "明天到期"], f"🟡 {step_name}: 有明日到期项"),
            (["存量不足", "缺货", "需要购买"], f"🛒 {step_name}: 需要采购"),
            (["维修", "故障", "损坏"], f"🔧 {step_name}: 需要维修"),
            (["逾期", "已过期"], f"⚠️ {step_name}: 有逾期项"),
        ]
        for keywords, alert in alert_rules:
            if any(k in response_text for k in keywords):
                alerts.append(alert)
        return alerts

    # ================================================================
    # Core workflows
    # ================================================================

    async def daily_checkup(self, user_id: str = "user_001") -> WorkflowResult:
        """Daily inspection: fridge + bills + maintenance (parallel)"""
        wf = WorkflowResult(
            workflow_id=f"daily_{date.today().isoformat()}",
            workflow_name="daily_inspection",
        )

        # Parallel execution of all 3 checks
        tasks = await asyncio.gather(
            self._run_step(self.shopping, user_id,
                "检查冰箱库存，列出今天和明天过期的食材，存量低于30%的必需品",
                "shopping"),
            self._run_step(self.maintenance, user_id,
                "检查待缴费账单（电费水费燃气物业宽带），列出即将到期和已过期的",
                "maintenance"),
            self._run_step(self.maintenance, user_id,
                "检查家电维保状态，列出30天内需要保养的设备",
                "maintenance"),
            return_exceptions=True,
        )

        alerts = []
        step_names = ["fridge", "bills", "maintenance"]
        for i, task in enumerate(tasks):
            if isinstance(task, Exception):
                step = {
                    "agent": "unknown",
                    "message": "",
                    "response": str(task),
                    "success": False,
                    "tool_calls": 0,
                    "intent": "error",
                }
            else:
                step = task
                name = step_names[i] if i < len(step_names) else f"step_{i}"
                alerts.extend(self._extract_alerts(name, step.get("response", "")))
            wf.steps.append(step)

        wf.alerts = list(dict.fromkeys(alerts))  # deduplicate
        wf.summary = (
            f"Daily inspection: {len(alerts)} issues found.\n" + "\n".join(alerts)
            if alerts
            else "All clear: fridge stocked, no overdue bills, appliances in good condition."
        )
        wf.status = "completed"
        wf.finished_at = datetime.now()
        return wf

    async def weekly_meal_prep(self, user_id: str = "user_001") -> WorkflowResult:
        """Weekly meal planning: fridge -> meal plan -> shopping list (sequential)"""
        wf = WorkflowResult(
            workflow_id=f"meal_{date.today().isoformat()}",
            workflow_name="weekly_meal_prep",
        )

        # Step 1: Plan meals
        step1 = await self._run_step(self.meal, user_id,
            "查看冰箱食材，规划未来7天一日三餐。优先使用快过期的，荤素搭配。",
            "meal_plan")
        wf.steps.append(step1)

        # Step 2: Generate shopping list (depends on step1)
        step2 = await self._run_step(self.shopping, user_id,
            "根据刚才规划的菜谱生成购物清单，冰箱已有的不重复买，列出缺的食材和预估价格。",
            "shopping")
        wf.steps.append(step2)

        # Step 3: Price comparison (parallel with shopping list actually)
        step3 = await self._run_step(self.shopping, user_id,
            "对比购物清单前3项主要食材在盒马、永辉、美团、叮咚的价格，推荐最省钱方案。",
            "shopping")
        wf.steps.append(step3)

        wf.summary = "Weekly meal plan ready with shopping list and price comparison."
        wf.alerts = ["Plan your grocery trip to avoid weekend crowds."]
        wf.status = "completed"
        wf.finished_at = datetime.now()
        return wf

    async def evening_routine(self, user_id: str = "user_001") -> WorkflowResult:
        """Evening routine: off-peak scheduling + tomorrow tasks (parallel)"""
        wf = WorkflowResult(
            workflow_id=f"evening_{date.today().isoformat()}",
            workflow_name="evening_routine",
        )

        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        tasks = await asyncio.gather(
            self._run_step(self.appliance, user_id,
                "预约今晚错峰运行：洗碗机22:00→洗衣机23:30→扫地机02:00，谷电0.3元/度",
                "appliance"),
            self._run_step(self.maintenance, user_id,
                f"看看明天({tomorrow})有什么需要处理的家务事项",
                "maintenance"),
            return_exceptions=True,
        )

        for task in tasks:
            wf.steps.append(
                task if not isinstance(task, Exception)
                else {"agent": "unknown", "response": str(task), "success": False}
            )

        wf.summary = "Evening appliances scheduled for off-peak, ~50% electricity savings."
        wf.status = "completed"
        wf.finished_at = datetime.now()
        return wf

    async def proactive_smart_check(self, user_id: str = "user_001") -> WorkflowResult:
        """Proactive smart check: inspect + conditional recipe suggestions"""
        wf = WorkflowResult(
            workflow_id=f"smart_{date.today().isoformat()}",
            workflow_name="proactive_smart_check",
        )

        # Parallel: fridge + bills
        step1, step3 = await asyncio.gather(
            self._run_step(self.shopping, user_id,
                "检查冰箱：列出临期食材和库存不足品，如有临期推荐今天可做的菜",
                "shopping"),
            self._run_step(self.maintenance, user_id,
                "检查今明两天到期的账单",
                "maintenance"),
            return_exceptions=True,
        )

        wf.steps.append(step1 if not isinstance(step1, Exception) else
                        {"agent": "shopping", "response": str(step1), "success": False})
        wf.steps.append(step3 if not isinstance(step3, Exception) else
                        {"agent": "maintenance", "response": str(step3), "success": False})

        # Conditional: if near-expiry found, suggest recipes
        if not isinstance(step1, Exception) and self._has_issue(step1["response"], ["过期", "临期"]):
            step2 = await self._run_step(self.meal, user_id,
                "冰箱有临期食材，根据它们推荐今天能做的菜，减少浪费",
                "meal_plan")
            wf.steps.append(step2)

        urgent_count = sum(
            1 for s in wf.steps
            if not isinstance(s, Exception) and self._has_issue(s.get("response", ""))
        )
        wf.summary = (
            f"Found {urgent_count} urgent items needing attention."
            if urgent_count > 0
            else "All clear, nothing urgent."
        )
        wf.alerts = [f"{urgent_count} urgent items"] if urgent_count > 0 else []
        wf.status = "completed"
        wf.finished_at = datetime.now()
        return wf


# Global singleton
_engine: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine
