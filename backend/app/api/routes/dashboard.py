"""
Dashboard 路由 — 自动化工作流结果 & 主动告警
"""
from fastapi import APIRouter, BackgroundTasks

from ...services.scheduler_service import get_scheduler
from ...services.workflow_engine import get_workflow_engine

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/alerts")
async def get_alerts():
    """获取当前所有待处理告警"""
    sched = get_scheduler()
    return {"alerts": sched.get_latest_alerts(), "count": len(sched.get_latest_alerts())}


@router.get("/history")
async def workflow_history(limit: int = 10, include_steps: bool = False):
    """查看自动化工作流历史。include_steps=true 返回每步的完整AI回复"""
    sched = get_scheduler()
    return {"results": sched.get_recent_results(limit, include_steps=include_steps)}


@router.get("/history/{workflow_id}")
async def workflow_detail(workflow_id: str):
    """查看某个工作流的详细步骤"""
    sched = get_scheduler()
    all_results = sched.get_recent_results(50, include_steps=True)
    for r in all_results:
        if r["workflow_id"] == workflow_id:
            return r
    return {"error": "Workflow not found"}


@router.post("/run/{workflow_type}")
async def trigger_workflow(workflow_type: str, background_tasks: BackgroundTasks, user_id: str = "user_001"):
    """手动触发工作流（立即执行）"""
    sched = get_scheduler()

    workflows = {
        "daily": sched.run_daily_checkup,
        "weekly": sched.run_weekly_meal_prep,
        "evening": sched.run_evening_routine,
        "smart": sched.run_proactive_check,
    }

    if workflow_type not in workflows:
        return {"error": f"Unknown workflow. Choose: {list(workflows.keys())}"}

    result = await workflows[workflow_type](user_id)
    return {
        "workflow_id": result.workflow_id,
        "workflow_name": result.workflow_name,
        "status": result.status,
        "summary": result.summary,
        "alerts": result.alerts,
        "steps": [
            {"agent": s["agent"], "response_preview": s["response"][:200]}
            for s in result.steps
        ],
    }


@router.get("/status")
async def dashboard_status():
    """仪表盘总览"""
    sched = get_scheduler()
    alerts = sched.get_latest_alerts()
    history = sched.get_recent_results(3)

    return {
        "alerts_count": len(alerts),
        "latest_alerts": alerts[:5],
        "recent_workflows": history,
        "available_workflows": [
            {"id": "daily", "name": "每日家庭巡检", "desc": "冰箱临期检查 + 账单提醒 + 维保状态"},
            {"id": "weekly", "name": "每周膳食规划", "desc": "查冰箱→排菜谱→购物清单→比价"},
            {"id": "evening", "name": "晚间自动化", "desc": "错峰预约家电 + 明日待办提醒"},
            {"id": "smart", "name": "主动智能检测", "desc": "6 Agent并行检测：购物+维保+安防 → 条件触发膳食"},
            {"id": "security", "name": "安防巡检", "desc": "全面检查门禁/监控/传感器/门窗状态"},
        ],
        "hint": "v5.0 工作流已升级为6 Agent协同，支持security_check和场景触发",
        "version": "5.0.0"
    }
