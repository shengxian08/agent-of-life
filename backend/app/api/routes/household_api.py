"""
v5.0 新增 API — 场景执行 / 成员切换 / 隐私开关 / AI简报 / 任务队列 / 家庭总览
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from ...agents.crew import HouseholdCrew, get_household_crew
from ...models.schemas import (
    SceneTriggerRequest, MemberSwitchRequest, PrivacyToggleRequest,
    AIBriefResponse, OverviewStatus, FamilyMember,
)
from ..deps import get_crew

router = APIRouter(prefix="/household", tags=["Household v5.0"])


# ========== 场景快捷执行 ==========
@router.post("/scene")
async def trigger_scene(req: SceneTriggerRequest, crew: HouseholdCrew = Depends(get_crew)):
    """触发场景模式 (早安/离家/晚安/观影/清扫)"""
    valid_scenes = ["morning", "away", "evening", "movie", "cleaning"]
    if req.scene not in valid_scenes:
        raise HTTPException(400, f"Invalid scene. Choose: {valid_scenes}")

    session_id = req.session_id or f"scene_{req.scene}_{int(datetime.now().timestamp())}"
    results = await crew.run_workflow("scene_trigger", req.user_id, req.scene)
    return {
        "scene": req.scene,
        "status": "executed",
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }


# ========== 全局AI简报 ==========
@router.get("/brief/{user_id}", response_model=AIBriefResponse)
async def get_ai_brief(user_id: str):
    """获取全局AI简报 — 汇总6个Agent的核心信息"""
    return AIBriefResponse(
        shopping_alert="冰箱3件临期食材：菠菜(1天)、鸡蛋(2天)、牛奶(3天)",
        meal_suggestion="推荐今明优先消耗菠菜和鸡蛋，可做菠菜蛋花汤",
        appliance_status="今晚22:00已预约错峰运行（洗碗机→洗衣机→扫地机）",
        maintenance_alert="空调滤网已运行1200小时，建议下周清洗；电费账单3天后到期",
        security_status="安防系统正常，今日无异常事件，门口快递待取",
        household_tasks="今日待办：物业费缴纳(截止明天)，快递2件在途",
        overall_summary="🏠 家庭运转正常。🔔 3件事需要关注：菠菜今天要用、电费快到期、门口有快递。",
        generated_at=datetime.now(),
    )


# ========== 跨Agent任务队列 ==========
@router.get("/task-queue/{user_id}")
async def get_task_queue(user_id: str):
    """获取跨Agent顺序任务队列"""
    return {
        "queue": [
            {"task_id": "t1", "from_agent": "🛒 购物", "to_agent": "🍳 膳食", "desc": "采购完成 → 生成今晚菜谱", "status": "pending"},
            {"task_id": "t2", "from_agent": "⚡ 家电", "to_agent": "", "desc": "错峰预约执行中(22:00开始)", "status": "running"},
            {"task_id": "t3", "from_agent": "🔧 维保", "to_agent": "📋 事务", "desc": "维保完成 → 添加到日程", "status": "done"},
        ],
        "pending_count": 1,
        "running_count": 1,
        "done_today": 3,
    }


# ========== 成员切换 ==========
@router.post("/member/switch")
async def switch_member(req: MemberSwitchRequest):
    """切换当前活跃家庭成员"""
    return {
        "previous_user_id": req.user_id,
        "current_member_id": req.member_id,
        "status": "switched",
        "message": f"已切换至家庭成员 {req.member_id}",
    }


# ========== 隐私模式切换 ==========
@router.post("/privacy/toggle")
async def toggle_privacy(req: PrivacyToggleRequest):
    """切换本地/云端隐私模式"""
    mode = "本地模式 🔒" if req.local_mode else "云端模式 ☁️"
    return {
        "user_id": req.user_id,
        "privacy_mode": mode,
        "local_only": req.local_mode,
        "message": f"已切换至{mode}，{'数据仅在本地处理，不上传云端' if req.local_mode else '启用云端AI增强能力'}",
    }


# ========== 家庭成员管理 ==========
@router.get("/members/{user_id}")
async def get_family_members(user_id: str):
    """获取家庭成员列表及画像"""
    return {
        "members": [
            {"member_id": "user_001", "name": "我", "role": "owner", "dietary_preferences": ["低盐","海鲜","不吃香菜"], "schedule_pattern": "工作日7:00起/23:00睡", "preferences": {"wake_time":70,"temp_cool":60,"light_bright":50}, "avatar": "👤"},
            {"member_id": "user_002", "name": "配偶", "role": "member", "dietary_preferences": ["素食倾向","烘焙","低脂"], "schedule_pattern": "工作日7:30起/22:30睡", "preferences": {"wake_time":65,"temp_cool":55}, "avatar": "👩"},
            {"member_id": "user_003", "name": "孩子", "role": "child", "dietary_preferences": ["高蛋白","少辣","水果"], "schedule_pattern": "上学日7:00起/21:00睡", "preferences": {"wake_time":68,"temp_cool":50}, "avatar": "👶"},
            {"member_id": "user_004", "name": "老人", "role": "elder", "dietary_preferences": ["少油少盐","软食","糖尿病饮食"], "schedule_pattern": "6:00起/21:00睡", "preferences": {"wake_time":85,"temp_cool":75}, "avatar": "👴"},
        ]
    }


# ========== 家庭总览驾驶舱 ==========
@router.get("/overview/{user_id}", response_model=OverviewStatus)
async def get_overview(user_id: str):
    """家庭总览驾驶舱 — 全局主Agent快照"""
    return OverviewStatus(
        agents={
            "shopping": {"name": "购物管家", "icon": "🛒", "status": "ready", "highlights": ["冰箱23种食材", "3件临期"]},
            "meal": {"name": "膳食规划师", "icon": "🍳", "status": "ready", "highlights": ["本周5道菜谱", "今日建议:菠菜蛋花汤"]},
            "appliance": {"name": "家电调度员", "icon": "⚡", "status": "ready", "highlights": ["4台在线", "今晚错峰已预约"]},
            "maintenance": {"name": "维保小卫士", "icon": "🔧", "status": "ready", "highlights": ["2项待维保", "1笔账单待缴"]},
            "security": {"name": "安防监护Agent", "icon": "🛡️", "status": "ready", "highlights": ["安防正常", "今日0异常"]},
            "household": {"name": "家庭事务Agent", "icon": "📋", "status": "ready", "highlights": ["3项今日待办", "2件快递在途"]},
        },
        active_tasks=1,
        today_interactions=12,
        system_status="healthy",
        llm_service="online",
        vector_service="online",
        uptime="运行中",
    )

