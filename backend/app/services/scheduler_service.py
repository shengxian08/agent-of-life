"""
定时调度服务 — 每天自动运行工作流，不等人催
"""
from datetime import datetime
from typing import Any
from collections import deque

from .workflow_engine import WorkflowEngine, WorkflowResult, get_workflow_engine


class SchedulerService:
    """定时任务调度器（内置轻量版，生产环境可换 APScheduler）"""

    def __init__(self):
        self.engine: WorkflowEngine | None = None
        self.results: deque[WorkflowResult] = deque(maxlen=50)  # 保留最近50条结果
        self._running = False

    def _get_engine(self) -> WorkflowEngine:
        if self.engine is None:
            self.engine = get_workflow_engine()
        return self.engine

    async def run_daily_checkup(self, user_id: str = "user_001") -> WorkflowResult:
        """每日巡检（建议每天早上8点执行）"""
        result = await self._get_engine().daily_checkup(user_id)
        self.results.appendleft(result)
        return result

    async def run_weekly_meal_prep(self, user_id: str = "user_001") -> WorkflowResult:
        """每周膳食规划（建议每周日早上执行）"""
        result = await self._get_engine().weekly_meal_prep(user_id)
        self.results.appendleft(result)
        return result

    async def run_evening_routine(self, user_id: str = "user_001") -> WorkflowResult:
        """晚间自动化（建议每晚9点执行）"""
        result = await self._get_engine().evening_routine(user_id)
        self.results.appendleft(result)
        return result

    async def run_proactive_check(self, user_id: str = "user_001") -> WorkflowResult:
        """主动智能检测（建议每4小时执行）"""
        result = await self._get_engine().proactive_smart_check(user_id)
        self.results.appendleft(result)
        return result

    def get_recent_results(self, limit: int = 10, include_steps: bool = False) -> list[dict[str, Any]]:
        """获取最近的工作流执行结果"""
        results = []
        for r in list(self.results)[:limit]:
            item = {
                "workflow_id": r.workflow_id,
                "workflow_name": r.workflow_name,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "summary": r.summary,
                "alerts": r.alerts,
                "steps_count": len(r.steps),
            }
            if include_steps:
                item["steps"] = [
                    {
                        "agent": s["agent"],
                        "message": s["message"],
                        "response": s["response"],  # 完整回复
                        "tool_calls": s["tool_calls"],
                    }
                    for s in r.steps
                ]
            results.append(item)
        return results

    def get_latest_alerts(self) -> list[str]:
        """获取最近的告警"""
        alerts = []
        for r in list(self.results)[:5]:
            alerts.extend(r.alerts)
        return list(dict.fromkeys(alerts))  # 去重保序


# 全局单例
_scheduler: SchedulerService | None = None

def get_scheduler() -> SchedulerService:
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler
