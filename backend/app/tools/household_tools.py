"""
家庭事务工具 — 日程/快递/物业/访客
"""
import hashlib
import json
from datetime import datetime, date
from typing import Any

import httpx
from loguru import logger

from ..config import settings


# 快递100 支持的快递公司编码
CARRIER_MAP = {
    "顺丰": "shunfeng", "圆通": "yuantong", "中通": "zhongtong",
    "申通": "shentong", "韵达": "yunda", "京东": "jd",
    "邮政": "ems", "极兔": "jtexpress", "德邦": "debangwuliu",
}

async def _get_user_tracking_numbers(user_id: str) -> list[dict]:
    """从数据库获取用户已保存的快递单号"""
    from ..models.database import get_db, TrackingNumber
    from sqlalchemy import select
    try:
        async for session in get_db():
            result = await session.execute(
                select(TrackingNumber).where(TrackingNumber.user_id == user_id)
            )
            return [
                {"tracking_id": r.tracking_id, "carrier": r.carrier, "desc": r.description or ""}
                for r in result.scalars()
            ]
    except Exception:
        return []


async def track_packages(user_id: str) -> dict[str, Any]:
    """追踪快递状态 — 快递100 实时查询 API

    配置方式：
      1. 注册 https://api.kuaidi100.com 获取 customer + key（免费额度100次/天）
      2. 在 .env 中设置 KUAIDI100_CUSTOMER 和 KUAIDI100_KEY
      3. 未配置时降级为模拟数据

    用户录入快递：
      数据库表 tracking_numbers (user_id, tracking_id, carrier, description)
      可通过对话让 Agent 调用 add_tracking 工具录入
    """
    customer = getattr(settings, 'kuaidi100_customer', '')
    api_key = getattr(settings, 'kuaidi100_key', '')

    # 获取用户已录入的快递单号
    tracking_list = await _get_user_tracking_numbers(user_id)

    # 未配置 API → 降级为模拟数据
    if not customer or not api_key:
        if not tracking_list:
            return {
                "packages": [
                    {"tracking_id": "SF1234567890", "carrier": "顺丰", "status": "派送中",
                     "eta": "今天 14:00-16:00", "desc": "网购食材"},
                    {"tracking_id": "YT9876543210", "carrier": "圆通", "status": "运输中",
                     "eta": "明天", "desc": "家电配件"},
                ],
                "total_in_transit": 2,
                "delivered_today": 0,
                "note": "模拟数据。配置 KUAIDI100_CUSTOMER + KUAIDI100_KEY 启用真实快递追踪",
            }
        # 有快递号但无 API → 返回录入信息
        return {
            "packages": [
                {"tracking_id": t["tracking_id"], "carrier": t["carrier"],
                 "status": "待查询（需配置快递100 API）", "desc": t.get("desc", "")}
                for t in tracking_list
            ],
            "total_in_transit": len(tracking_list),
            "delivered_today": 0,
            "note": "配置 KUAIDI100_CUSTOMER + KUAIDI100_KEY 后显示实时状态",
        }

    # 真实 API 查询
    packages = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for t in (tracking_list or [{"tracking_id": "SF1234567890", "carrier": "顺丰", "desc": ""}]):
            carrier_code = CARRIER_MAP.get(t["carrier"], "auto")
            param = json.dumps({"com": carrier_code, "num": t["tracking_id"]})
            sign = hashlib.md5(f"{param}{api_key}{customer}".encode()).hexdigest().upper()

            try:
                resp = await client.post(
                    "https://poll.kuaidi100.com/poll/query.do",
                    data={
                        "customer": customer,
                        "sign": sign,
                        "param": param,
                    }
                )
                data = resp.json()
                if data.get("state") in ("0", "1", "2", "3"):
                    latest = data.get("data", [{}])[0] if data.get("data") else {}
                    packages.append({
                        "tracking_id": t["tracking_id"],
                        "carrier": t["carrier"],
                        "status": _translate_status(data.get("state", "0")),
                        "latest_context": latest.get("context", ""),
                        "latest_time": latest.get("time", ""),
                        "desc": t.get("desc", ""),
                    })
                else:
                    packages.append({
                        "tracking_id": t["tracking_id"], "carrier": t["carrier"],
                        "status": "查询失败", "desc": data.get("message", "无结果"),
                    })
            except Exception as e:
                logger.warning(f"Kuaidi100 query failed for {t['tracking_id']}: {e}")
                packages.append({
                    "tracking_id": t["tracking_id"], "carrier": t["carrier"],
                    "status": "查询异常", "desc": str(e)[:100],
                })

    return {
        "packages": packages,
        "total_in_transit": len(packages),
        "delivered_today": sum(1 for p in packages if "已签收" in p.get("status", "")),
    }


def _translate_status(state: str) -> str:
    return {"0": "运输中", "1": "已签收", "2": "问题件", "3": "已退回"}.get(state, state)


async def add_tracking(user_id: str, tracking_id: str, carrier: str = "顺丰",
                       description: str = "") -> dict[str, Any]:
    """录入快递单号到数据库"""
    from ..models.database import get_db, TrackingNumber
    from sqlalchemy import select
    try:
        async for session in get_db():
            existing = await session.execute(
                select(TrackingNumber).where(
                    TrackingNumber.user_id == user_id,
                    TrackingNumber.tracking_id == tracking_id,
                )
            )
            if existing.scalars().first():
                return {"status": "exists", "tracking_id": tracking_id, "message": "该快递已录入"}
            session.add(TrackingNumber(
                user_id=user_id, tracking_id=tracking_id,
                carrier=carrier, description=description,
            ))
            await session.commit()
        return {"status": "added", "tracking_id": tracking_id, "carrier": carrier}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


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

