"""
安防监护工具 — 门禁/监控/传感器/老人看护
"""
from datetime import datetime
from typing import Any


async def check_door_status(user_id: str) -> dict[str, Any]:
    """检查全部门锁状态"""
    return {
        "doors": [
            {"name": "入户门", "status": "locked", "last_event": "今天 08:30 离家上锁", "battery": "85%"},
            {"name": "阳台门", "status": "closed", "last_event": "昨天 22:00 关闭"},
            {"name": "车库门", "status": "locked", "last_event": "昨天 18:30 关闭", "battery": "60%"},
        ],
        "summary": "全部安全，3扇门均已锁闭",
    }


async def check_window_status(user_id: str) -> dict[str, Any]:
    """检查所有窗户状态"""
    return {
        "windows": [
            {"name": "客厅窗", "status": "closed", "room": "客厅"},
            {"name": "主卧窗", "status": "closed", "room": "主卧"},
            {"name": "次卧窗", "status": "tilted", "room": "次卧"},
            {"name": "厨房窗", "status": "closed", "room": "厨房"},
        ],
        "summary": "次卧窗户微开通风，其余正常",
        "alerts": [{"level": "info", "msg": "次卧窗户处于微开状态，如离家请关闭"}],
    }


async def check_camera_feeds(user_id: str) -> dict[str, Any]:
    """检查摄像头画面"""
    return {
        "cameras": [
            {"name": "门口摄像头", "status": "online", "last_motion": "5分钟前（快递员）", "resolution": "1080p"},
            {"name": "客厅摄像头", "status": "online", "last_motion": "无", "resolution": "1080p"},
            {"name": "儿童房摄像头", "status": "online", "last_motion": "2分钟前", "resolution": "720p"},
        ],
        "summary": "3个摄像头在线，画面正常",
        "today_events": [
            {"time": "08:30", "event": "家人离家"},
            {"time": "10:15", "event": "快递员按门铃"},
            {"time": "10:16", "event": "快递放入门口"},
        ],
    }


async def get_security_events(user_id: str, limit: int = 10) -> dict[str, Any]:
    """获取安防事件日志"""
    return {
        "events": [
            {"time": "10:15", "type": "visitor", "desc": "快递员按门铃", "level": "info"},
            {"time": "08:30", "type": "arm", "desc": "离家设防已启动", "level": "info"},
            {"time": "昨天 20:00", "type": "motion", "desc": "客厅检测到移动（正常）", "level": "info"},
        ],
        "total_today": 3,
        "alerts": [],
    }


async def set_away_mode(user_id: str) -> dict[str, Any]:
    """设置离家布防模式"""
    return {
        "status": "armed",
        "actions": [
            "全部门窗检查 → 已锁闭",
            "安防摄像头 → 已开启移动侦测",
            "烟雾/燃气传感器 → 在线",
            "所有智能灯 → 已关闭",
            "家电 → 已切换至节能模式",
        ],
        "message": "离家布防已启动，安防系统全面值守中 🔒",
        "armed_at": datetime.now().isoformat(),
    }


async def get_elderly_activity(user_id: str) -> dict[str, Any]:
    """获取老人活动状态"""
    return {
        "status": "normal",
        "last_activity": "10:30 客厅走动",
        "today_summary": "早上6:30起床，7:00厨房活动，8:00-10:00客厅看电视，活动规律正常",
        "alerts": [],
    }

