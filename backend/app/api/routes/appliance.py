"""
家电调度路由
"""
from fastapi import APIRouter, Body

from ...tools.appliance_tools import (
    get_appliance_status, schedule_appliance,
    generate_off_peak_schedule, control_smart_appliance,
)

router = APIRouter(prefix="/appliance", tags=["Appliance"])


@router.get("/status/{user_id}")
async def appliance_status(user_id: str):
    """获取家电状态"""
    return {"appliances": await get_appliance_status(user_id)}


@router.post("/schedule/{user_id}")
async def create_schedule(
    user_id: str,
    appliance_id: str = Body(...),
    start_time: str = Body(...),
    task: str = Body("标准运行"),
    force_off_peak: bool = Body(True),
):
    """预约家电运行"""
    from datetime import time
    h, m = map(int, start_time.split(":"))
    return await schedule_appliance(user_id, appliance_id, time(h, m), task=task, force_off_peak=force_off_peak)


@router.post("/off-peak/{user_id}")
async def off_peak_plan(user_id: str, date_str: str = Body("", embed=True)):
    """生成错峰计划"""
    return await generate_off_peak_schedule(user_id, date_str)


@router.post("/control/{user_id}")
async def control_appliance(
    user_id: str,
    appliance_id: str = Body(...),
    action: str = Body(...),
):
    """控制智能家电"""
    return await control_smart_appliance(user_id, appliance_id, action)
