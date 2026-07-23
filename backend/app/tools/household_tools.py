"""
家庭事务工具 — 日程/快递/物业/访客
"""
from datetime import datetime, date, timedelta
from typing import Any


async def track_packages(user_id: str) -> dict[str, Any]:
    """追踪快递状态"""
    return {
        "packages": [
            {"tracking_id": "SF1234567890", "carrier": "顺丰", "status": "派送中", "eta": "今天 14:00-16:00", "desc": "网购食材"},
            {"tracking_id": "YT9876543210", "carrier": "圆通", "status": "运输中", "eta": "明天", "desc": "家电配件"},
        ],
        "total_in_transit": 2,
        "delivered_today": 0,
    }


async def get_community_notices(user_id: str) -> dict[str, Any]:
    """获取社区通知"""
    return {
        "notices": [
            {"date": "2026-07-22", "title": "电梯维保通知", "detail": "7月22日 10:00-12:00 2号电梯停运维保"},
            {"date": "2026-07-25", "title": "水费账单", "detail": "本期水费 86.50 元，请于7月30日前缴纳"},
        ],
        "upcoming_events": [
            {"date": "2026-07-28", "title": "社区夏日集市", "time": "15:00-20:00", "location": "中心广场"},
        ],
    }


async def get_family_schedule(user_id: str, days: int = 7) -> dict[str, Any]:
    """获取家庭日程总览"""
    start = date.today()
    events = []
    for i in range(days):
        d = start + timedelta(days=i)
        day_events = []
        if d.weekday() < 5:  # weekday
            day_events = [
                {"time": "07:00", "event": "起床", "member": "全家"},
                {"time": "08:00", "event": "上班/上学", "member": "我 & 孩子"},
                {"time": "18:30", "event": "晚餐", "member": "全家"},
            ]
        else:
            day_events = [
                {"time": "09:00", "event": "晨练", "member": "老人"},
                {"time": "10:00", "event": "超市采购", "member": "我"},
                {"time": "15:00", "event": "兴趣班", "member": "孩子"},
            ]
        # Special events
        if d == start + timedelta(days=3):
            day_events.append({"time": "10:00", "event": "物业维修预约", "member": "维修师傅"})
        events.append({"date": d.isoformat(), "day_of_week": ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()], "events": day_events})
    return {"schedule": events, "member_count": 4}

