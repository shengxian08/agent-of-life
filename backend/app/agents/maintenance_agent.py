"""
维保 Agent — LLM 驱动，家电保养、维修联系、缴费提醒
"""
from .base_agent import BaseAgent

MAINTENANCE_PROMPT = """你是家庭维保管家。家电维保记录：石头扫地机器人 G20 上次保养 2026-06-01 每90天一次、海尔洗衣机 EG100 上次 2026-05-15 每180天、西门子洗碗机 SN656X 上次 2026-04-01 每180天、格力空调 KFR-35GW 上次 2026-03-01 每365天。

职责：维保检查、找维修师傅、账单管理、发送提醒。

回复要求：
- 口语化中文，像物管跟你汇报一样
- 禁止 Markdown 格式（不要 # | ** `）
- 状态用 emoji 标注：🔴已过期 🟡7天内 🟢30天内 ✅正常
- 每台家电一行，最后给出行动建议"""

class MaintenanceAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="maintenance_agent",
            description="维保管家：保养检查、维修联系、缴费提醒",
            system_prompt=MAINTENANCE_PROMPT,
            tools=["check_maintenance_due", "create_maintenance_task",
                   "find_service_contact", "send_maintenance_reminder",
                   "send_bill_reminder", "send_notification"],
        )