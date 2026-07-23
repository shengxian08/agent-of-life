"""
维保管理路由
"""
from fastapi import APIRouter, Body

from ...tools.maintenance_tools import (
    check_maintenance_due, create_maintenance_task,
    find_service_contact, send_maintenance_reminder,
)
from ...tools.notification_tools import send_bill_reminder

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@router.get("/check/{user_id}")
async def check_due(user_id: str):
    """检查维保到期"""
    return {"items": await check_maintenance_due(user_id)}


@router.post("/task/{user_id}")
async def create_task(
    user_id: str,
    appliance_id: str = Body(...),
    appliance_name: str = Body(...),
    task_type: str = Body(...),
    description: str = Body(...),
    priority: str = Body("medium"),
):
    """创建维保任务"""
    task = await create_maintenance_task(
        user_id, appliance_id, appliance_name, task_type, description, priority
    )
    return task.model_dump()


@router.get("/contacts")
async def find_contacts(
    appliance_type: str = "综合",
    location: str = "朝阳区",
):
    """查找维修师傅"""
    contacts = await find_service_contact(appliance_type, location)
    return {"appliance_type": appliance_type, "contacts": contacts}


@router.get("/bills/{user_id}")
async def check_bills(user_id: str):
    """检查缴费账单"""
    return await send_bill_reminder(user_id)
