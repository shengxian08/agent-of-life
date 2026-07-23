"""
日历工具 - 日程管理、空闲时段查找
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any

_event_lock = asyncio.Lock()

_MOCK_EVENTS: list[dict[str, Any]] = [
    {"event_id": "e001", "title": "工作会议", "date": "2026-07-19", "start": "09:00", "end": "10:30"},
    {"event_id": "e002", "title": "接送孩子", "date": "2026-07-19", "start": "17:00", "end": "17:30"},
    {"event_id": "e003", "title": "健身", "date": "2026-07-20", "start": "18:00", "end": "19:00"},
    {"event_id": "e004", "title": "超市采购", "date": "2026-07-20", "start": "10:00", "end": "11:00"},
]


async def get_weekly_schedule(
    user_id: str, start_date: date | None = None
) -> list[dict[str, Any]]:
    """获取一周日程"""
    if start_date is None:
        start_date = date.today()
    end_date = start_date + timedelta(days=7)

    result = []
    for event in _MOCK_EVENTS:
        event_date = date.fromisoformat(event["date"])
        if start_date <= event_date < end_date:
            result.append(event)

    result.sort(key=lambda x: (x["date"], x["start"]))
    return result


async def add_calendar_event(
    user_id: str,
    title: str,
    event_date: date,
    start_time: time,
    end_time: time,
    description: str = "",
) -> dict[str, Any]:
    """添加日历事件"""
    async with _event_lock:
        event = {
            "event_id": f"e{len(_MOCK_EVENTS) + 1:04d}",
            "title": title,
            "date": event_date.isoformat(),
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "description": description,
        }
        _MOCK_EVENTS.append(event)
    return event


async def find_free_time_slots(
    user_id: str,
    target_date: date,
    min_duration_minutes: int = 60,
) -> list[dict[str, Any]]:
    """查找指定日期的空闲时段"""
    busy_slots = []
    for event in _MOCK_EVENTS:
        if event["date"] == target_date.isoformat():
            start_h, start_m = map(int, event["start"].split(":"))
            end_h, end_m = map(int, event["end"].split(":"))
            busy_slots.append((start_h * 60 + start_m, end_h * 60 + end_m))

    busy_slots.sort()

    free_slots = []
    day_start = 8 * 60  # 早8点
    day_end = 22 * 60   # 晚10点
    cursor = day_start

    for bs_start, bs_end in busy_slots:
        if cursor < bs_start and (bs_start - cursor) >= min_duration_minutes:
            free_slots.append({
                "start": f"{cursor // 60:02d}:{cursor % 60:02d}",
                "end": f"{bs_start // 60:02d}:{bs_start % 60:02d}",
                "duration_minutes": bs_start - cursor,
            })
        cursor = max(cursor, bs_end)

    if day_end - cursor >= min_duration_minutes:
        free_slots.append({
            "start": f"{cursor // 60:02d}:{cursor % 60:02d}",
            "end": f"{day_end // 60:02d}:{day_end % 60:02d}",
            "duration_minutes": day_end - cursor,
        })

    return free_slots


async def schedule_task(
    user_id: str,
    task_name: str,
    target_date: date,
    duration_minutes: int,
    preferred_time: str = "morning",
) -> dict[str, Any]:
    """智能安排任务到空闲时段"""
    slots = await find_free_time_slots(user_id, target_date, duration_minutes)

    if not slots:
        return {"error": "当日无足够的空闲时段", "suggest_next_day": (target_date + timedelta(days=1)).isoformat()}

    # 按偏好选择时段
    selected = None
    if preferred_time == "morning":
        selected = slots[0]
    elif preferred_time == "afternoon":
        for s in slots:
            h = int(s["start"].split(":")[0])
            if 12 <= h < 17:
                selected = s
                break
        if selected is None:
            selected = slots[len(slots) // 2]
    elif preferred_time == "evening":
        selected = slots[-1]
    else:
        selected = slots[0]

    start_parts = selected["start"].split(":")
    start_h, start_m = int(start_parts[0]), int(start_parts[1])
    start_time = time(start_h, start_m)

    # 计算实际结束时间：开始时间 + 任务时长
    total_minutes = start_h * 60 + start_m + duration_minutes
    end_h, end_m = divmod(total_minutes, 60)
    if end_h >= 24:
        end_h -= 24
    end_time = time(end_h, end_m)

    return await add_calendar_event(
        user_id, task_name, target_date, start_time, end_time
    )
