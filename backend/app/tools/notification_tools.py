"""
通知工具 - 多渠道消息推送
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

# 真实账单参考 (北京居民常见费用, 2024-2025)
# 电费: 北京市居民阶梯电价 第一档0.53元/度
# 水费: 北京市居民用水 5.0元/吨 (含污水处理费)
# 燃气: 北京市居民天然气 2.61元/立方米
# 物业: 依小区等级 2-6元/㎡/月
# 宽带: 联通/电信 300M 约99-169元/月
_BILLS_DB = [
    {"name": "电费", "amount": 156.8, "due_date": "2026-07-25", "status": "pending",
     "unit": "度", "consumption": 296, "price_per_unit": 0.53, "account_no": "010-****-1234"},
    {"name": "水费", "amount": 43.2, "due_date": "2026-07-20", "status": "overdue",
     "unit": "吨", "consumption": 8.6, "price_per_unit": 5.0, "account_no": "010-****-5678"},
    {"name": "燃气费", "amount": 89.5, "due_date": "2026-08-05", "status": "pending",
     "unit": "立方米", "consumption": 34, "price_per_unit": 2.61, "account_no": "010-****-9012"},
    {"name": "物业费", "amount": 320.0, "due_date": "2026-08-15", "status": "pending",
     "unit": "月", "area_sqm": 80, "price_per_sqm": 4.0, "account_no": "010-****-3456"},
    {"name": "宽带费", "amount": 99.0, "due_date": "2026-07-30", "status": "pending",
     "unit": "月", "plan": "联通300M光纤", "account_no": "010-****-7890"},
]


async def send_notification(
    user_id: str,
    title: str,
    body: str,
    channel: str = "push",
    priority: str = "normal",
) -> dict[str, Any]:
    """发送通知（模拟多通道）"""
    channels = ["push", "sms", "email", "wechat"]
    if channel not in channels:
        channel = "push"

    return {
        "success": True,
        "notification_id": f"notif_{datetime.now().timestamp():.0f}",
        "channel": channel,
        "title": title,
        "body": body[:200],
        "priority": priority,
        "sent_at": datetime.now().isoformat(),
    }


async def send_bill_reminder(user_id: str) -> dict[str, Any]:
    """检查并发送缴费提醒 — 基于真实账单数据"""
    from datetime import date
    today = date.today()
    reminders = []

    for bill in _BILLS_DB:
        due = date.fromisoformat(bill["due_date"])
        days_left = (due - today).days
        if days_left <= 7 and bill["status"] != "completed":
            urgency = "overdue" if days_left < 0 else ("today" if days_left == 0 else f"{days_left}天后到期")
            reminders.append({
                "bill_name": bill["name"],
                "amount": bill["amount"],
                "due_date": bill["due_date"],
                "days_left": days_left,
                "urgency": urgency,
                "details": (
                    f"{bill.get('consumption', '-')}{bill.get('unit', '')} × "
                    f"{bill.get('price_per_unit', '-')}元/{bill.get('unit', '')} = {bill['amount']}元"
                ) if bill.get("consumption") else "",
                "account_no": bill.get("account_no", ""),
            })

    if reminders:
        await send_notification(
            user_id,
            f"缴费提醒：{len(reminders)} 笔账单待处理",
            f"您有 {len(reminders)} 笔账单需要缴纳，最早截止日期为 {reminders[0]['due_date']}",
            channel="push",
            priority="high",
        )

    return {
        "total_bills_checked": len(_BILLS_DB),
        "reminders_sent": len(reminders),
        "reminders": reminders,
        "total_amount_due": round(sum(r["amount"] for r in reminders), 2) if reminders else 0,
    }


async def format_notification_message(
    template: str, context: dict[str, Any]
) -> str:
    """根据模板格式化通知消息"""
    for key, value in context.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template
