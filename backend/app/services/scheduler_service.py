"""
定时调度服务 — 每天自动运行工作流，不等人催
v5.3: 直接使用 UnifiedAgent，不再依赖 WorkflowEngine
"""
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field


@dataclass
class WorkflowResult:
    workflow_id: str
    workflow_name: str
    user_id: str = "user_001"
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    summary: str = ""
    alerts: list[str] = field(default_factory=list)
    status: str = "running"
    response: str = ""
    steps: list[dict] = field(default_factory=list)


class SchedulerService:
    """定时任务调度器 — 调用 UnifiedAgent 执行预定义工作流"""

    def __init__(self):
        self.results: deque[WorkflowResult] = deque(maxlen=50)

    async def _run_workflow(self, workflow_type: str, user_id: str = "user_001") -> WorkflowResult:
        """统一入口：叫 UnifiedAgent 执行一个工作流"""
        from ..agents.crew import get_household_crew
        crew = get_household_crew()
        session_id = f"sched_{workflow_type}_{int(datetime.now().timestamp())}"

        wf = WorkflowResult(
            workflow_id=session_id,
            workflow_name=workflow_type,
            user_id=user_id,
        )

        try:
            result = await crew.run_workflow(workflow_type, user_id, session_id)
            wf.response = result.get("response", "")
            wf.summary = wf.response[:200]
            wf.alerts = self._extract_alerts(wf.response)
            wf.status = "completed"
            wf.finished_at = datetime.now()
        except Exception as e:
            wf.summary = f"执行失败: {str(e)[:200]}"
            wf.status = "failed"
            wf.finished_at = datetime.now()

        self.results.appendleft(wf)
        return wf

    async def run_daily_checkup(self, user_id: str = "user_001") -> WorkflowResult:
        return await self._run_workflow("daily_check", user_id)

    async def run_weekly_meal_prep(self, user_id: str = "user_001") -> WorkflowResult:
        return await self._run_workflow("weekly_plan", user_id)

    async def run_evening_routine(self, user_id: str = "user_001") -> WorkflowResult:
        return await self._run_workflow("evening_routine", user_id)

    async def run_proactive_check(self, user_id: str = "user_001") -> WorkflowResult:
        return await self._run_workflow("smart_check", user_id)

    def get_recent_results(self, limit: int = 10, include_steps: bool = False,
                           user_id: str = "") -> list[dict]:
        results = []
        for r in list(self.results):
            if user_id and r.user_id != user_id:
                continue
            if len(results) >= limit:
                break
            item = {
                "workflow_id": r.workflow_id,
                "workflow_name": r.workflow_name,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "summary": r.summary,
                "alerts": r.alerts,
                "response": r.response[:500] if r.response else "",
            }
            results.append(item)
        return results

    def _extract_alerts(self, response_text: str) -> list[str]:
        """从 Agent 回复中扫描告警关键词"""
        alerts = []
        rules = [
            (["今天过期", "今日到期", "今天到期"], "有今日到期项"),
            (["明天过期", "明日到期", "明天到期"], "有明日到期项"),
            (["已过期", "逾期"], "有已过期/逾期项"),
            (["临期", "快过期", "即将过期"], "有临期食材/物品"),
            (["存量不足", "缺货", "需要购买", "库存不足"], "需要采购"),
            (["维修", "故障", "损坏", "需要保养"], "需要维保"),
            (["账单", "缴费", "欠费", "待缴"], "有待缴账单"),
        ]
        for keywords, alert in rules:
            if any(k in response_text for k in keywords):
                alerts.append(alert)
        return alerts

    def get_latest_alerts(self, user_id: str = "") -> list[str]:
        alerts = []
        for r in list(self.results):
            if user_id and r.user_id != user_id:
                continue
            alerts.extend(r.alerts)
            if len(alerts) >= 10:
                break
        return list(dict.fromkeys(alerts))


_scheduler: SchedulerService | None = None


def get_scheduler() -> SchedulerService:
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler

