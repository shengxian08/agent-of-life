"""
安防监护 Agent v5.0 — 门禁管理、监控巡检、异常预警、老人儿童看护
"""
from .base_agent import BaseAgent

SECURITY_PROMPT = """你是家庭安防监护专家。你的职责：

1. 门禁管理：查看门口/车库/单元门状态，远程开关门锁
2. 监控巡检：检查各摄像头画面，发现异常及时报告
3. 异常预警：检测门窗状态、烟雾/燃气报警、水浸传感器
4. 老人儿童看护：关注老人活动规律、儿童安全区域

回复要求：
- 口语化中文，像安全主管汇报
- 禁止 Markdown 格式
- 用 emoji 做视觉分隔
- 异常情况用明确的语言描述位置和风险等级"""

class SecurityAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="security_agent",
            description="安防监护Agent：门禁管理、监控巡检、异常预警、老人儿童看护",
            system_prompt=SECURITY_PROMPT,
            tools=[
                "check_door_status", "check_window_status",
                "check_camera_feeds", "get_security_events",
                "set_away_mode", "get_elderly_activity",
                "send_notification",
            ],
        )

