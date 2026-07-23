"""
家电工具 v4.0 — 基于真实家电型号参数 + 中国电价标准
数据来源：
- 家电参数：各品牌官网公开规格
- 能耗标准：中国能效标识网
- 电费标准：北京市居民阶梯电价 (发改委2024)
  · 峰电 8:00-22:00: 0.53元/度 (第一档)
  · 谷电 22:00-8:00: 0.30元/度
  · 第一档 0-2880度/年，第二档 +0.05，第三档 +0.30
"""
from datetime import date, time, datetime
from typing import Any

# ================================================================
# 真实家电数据库 (主流在售型号, 2024-2025)
# ================================================================

REAL_APPLIANCES = [
    {
        "appliance_id": "ap001",
        "name": "石头P20 Pro 扫地机器人",
        "appliance_type": "robot_vacuum",
        "brand": "石头科技(Roborock)",
        "model": "P20 Pro",
        "rated_power_w": 60,
        "typical_duration_min": 120,
        "energy_per_use_kwh": 0.12,      # 全屋清扫一次耗电
        "is_smart": True,
        "off_peak_only": True,
        "noise_db": 63,
        "water_tank_ml": 300,
        "dust_bag_capacity_ml": 400,
    },
    {
        "appliance_id": "ap002",
        "name": "海尔精华洗EG100",
        "appliance_type": "washing_machine",
        "brand": "海尔(Haier)",
        "model": "EG100MATESL59S",
        "rated_power_w": 350,
        "typical_duration_min": 58,
        "energy_per_use_kwh": 0.25,       # 混合洗一次
        "water_per_use_l": 42,
        "capacity_kg": 10,
        "is_smart": True,
        "off_peak_only": True,
        "noise_db": 52,
    },
    {
        "appliance_id": "ap003",
        "name": "西门子极净魔盒洗碗机",
        "appliance_type": "dishwasher",
        "brand": "西门子(Siemens)",
        "model": "SN656X26IC",
        "rated_power_w": 2400,
        "typical_duration_min": 90,       # 标准洗
        "energy_per_use_kwh": 0.85,       # 标准洗耗电
        "water_per_use_l": 9.5,
        "capacity_sets": 13,
        "is_smart": True,
        "off_peak_only": True,
        "noise_db": 42,
    },
    {
        "appliance_id": "ap004",
        "name": "美的理想家3代中央空调",
        "appliance_type": "air_conditioner",
        "brand": "美的(Midea)",
        "model": "MDS-120W",
        "rated_power_w": 3000,
        "typical_duration_min": 480,      # 夏季日均运行8小时
        "energy_per_use_hour_kwh": 0.8,   # 变频，低频运行时约0.8度/时
        "cooling_capacity_w": 12000,
        "is_smart": True,
        "off_peak_only": False,
        "noise_db": 38,
    },
    {
        "appliance_id": "ap005",
        "name": "海尔双变频冰箱",
        "appliance_type": "refrigerator",
        "brand": "海尔(Haier)",
        "model": "BCD-500WGHTD",
        "rated_power_w": 120,
        "energy_per_day_kwh": 0.85,      # 日均耗电(综合)
        "capacity_l": 500,
        "is_smart": True,
        "off_peak_only": False,           # 冰箱24小时运行
        "noise_db": 35,
    },
]

# 北京市居民电价 (2024年标准)
ELECTRICITY_PRICE = {
    "peak": {"hours": (8, 22), "price_per_kwh": 0.53, "name": "峰电"},
    "valley": {"hours": (22, 8), "price_per_kwh": 0.30, "name": "谷电"},
}


async def get_appliance_status(user_id: str) -> list[dict]:
    """获取家电状态 — 基于真实型号数据"""
    return [
        {
            "appliance_id": ap["appliance_id"],
            "name": ap["name"],
            "appliance_type": ap["appliance_type"],
            "brand": ap["brand"],
            "model": ap["model"],
            "is_smart": ap["is_smart"],
            "off_peak_only": ap["off_peak_only"],
            "rated_power_w": ap["rated_power_w"],
            "energy_per_use_kwh": ap.get("energy_per_use_kwh"),
            "status": "在线" if ap["is_smart"] else "非智能(需手动)",
        }
        for ap in REAL_APPLIANCES
    ]


async def schedule_appliance(
    user_id: str,
    appliance_id: str,
    start_time: str,
    end_time: str | None = None,
    task: str = "标准运行",
    force_off_peak: bool = True,
) -> dict:
    """预约家电运行 — 基于真实功率和电价计算费用"""
    ap = next((a for a in REAL_APPLIANCES if a["appliance_id"] == appliance_id), None)
    if not ap:
        return {"error": f"家电不存在: {appliance_id}"}

    # 解析开始时间
    try:
        h, m = map(int, start_time.split(":")[:2])
        st = time(h, m)
    except ValueError:
        return {"error": f"时间格式错误: {start_time}"}

    # 根据任务类型调整时长
    duration_map = {
        "标准洗": ap.get("typical_duration_min", 60),
        "快洗": max(ap.get("typical_duration_min", 60) // 2, 15),
        "强力洗": int(ap.get("typical_duration_min", 60) * 1.5),
        "节能洗": int(ap.get("typical_duration_min", 60) * 0.7),
        "混合洗": ap.get("typical_duration_min", 58),
        "快速": 15,
        "全屋清扫": ap.get("typical_duration_min", 120),
        "区域清扫": 30,
        "制冷": 480,
        "除湿": 240,
    }
    duration_min = duration_map.get(task, ap.get("typical_duration_min", 60))

    # 如果提供了 end_time，从时间差计算实际时长
    if end_time:
        try:
            eh, em = map(int, end_time.split(":")[:2])
            et = time(eh, em)
            end_minutes = eh * 60 + em
            start_minutes = h * 60 + m
            if end_minutes <= start_minutes:
                end_minutes += 24 * 60  # 跨天
            duration_min = end_minutes - start_minutes
        except ValueError:
            pass  # 忽略无效 end_time

    # 判断是否在谷电时段
    is_off_peak = st >= time(22, 0) or st < time(8, 0)
    price_per_kwh = ELECTRICITY_PRICE["valley"]["price_per_kwh"] if is_off_peak else ELECTRICITY_PRICE["peak"]["price_per_kwh"]

    energy_kwh = (ap.get("energy_per_use_kwh") or ap["rated_power_w"] / 1000 * duration_min / 60)

    # 按比例调整能耗
    if task in duration_map:
        ratio = duration_min / ap.get("typical_duration_min", 60)
        energy_kwh = energy_kwh * ratio

    cost = round(energy_kwh * price_per_kwh, 2)

    # 如果强制错峰但用户在峰电时段预约
    warning = ""
    if force_off_peak and not is_off_peak:
        peak_start = start_time
        off_peak_time = "22:00"
        cost_off_peak = round(energy_kwh * ELECTRICITY_PRICE["valley"]["price_per_kwh"], 2)
        warning = (
            f"当前时间为峰电时段({price_per_kwh}元/度)。"
            f"建议改为{off_peak_time}后运行，可节省{cost - cost_off_peak:.1f}元(谷电{ELECTRICITY_PRICE['valley']['price_per_kwh']}元/度)"
        )

    return {
        "appliance_id": appliance_id,
        "appliance_name": ap["name"],
        "brand_model": f"{ap['brand']} {ap['model']}",
        "task": task,
        "start_time": start_time,
        "duration_minutes": duration_min,
        "estimated_energy_kwh": round(energy_kwh, 3),
        "is_off_peak": is_off_peak,
        "electricity_price_per_kwh": price_per_kwh,
        "estimated_cost_yuan": cost,
        "warning": warning,
        "peak_vs_valley_savings": (
            f"谷电运行比峰电节省约{round(energy_kwh * (0.53 - 0.30), 2)}元"
            if is_off_peak else
            f"如在谷电运行可节省约{round(energy_kwh * (0.53 - 0.30), 2)}元"
        ),
    }


async def generate_off_peak_schedule(
    user_id: str,
    date_str: str = "",
) -> dict:
    """一键生成今晚错峰计划 — 基于真实家电功率优化排序

    排序策略：按功率从高到低 → 先跑大功率设备(更省)
    时间间隔：预留设备散热/人工操作缓冲
    """
    target_date = date_str or date.today().isoformat()

    # 过滤错峰设备并按功率排序
    off_peak_devices = sorted(
        [a for a in REAL_APPLIANCES if a.get("off_peak_only")],
        key=lambda x: x["rated_power_w"],
        reverse=True,
    )

    schedule = []
    total_cost = 0
    total_energy = 0
    # 22:00 谷电开始，按累计时间顺序调度
    next_start_hour = 22.0  # 22:00

    for ap in off_peak_devices:
        dur = ap.get("typical_duration_min", 60)
        # 当前设备开始时间 = 累计时间
        start_h = next_start_hour
        start_h_int = int(start_h)
        start_m = int((start_h - start_h_int) * 60)
        # 次日凌晨处理
        if start_h_int >= 24:
            start_h_int -= 24
        start_time_str = f"{start_h_int:02d}:{start_m:02d}"

        energy = ap.get("energy_per_use_kwh", ap["rated_power_w"] / 1000 * dur / 60)
        cost = round(energy * ELECTRICITY_PRICE["valley"]["price_per_kwh"], 2)
        total_cost += cost
        total_energy += energy

        task_names = {
            "ap003": "标准洗",
            "ap002": "混合洗",
            "ap001": "全屋清扫",
        }
        task = task_names.get(ap["appliance_id"], "标准运行")

        schedule.append({
            "appliance_id": ap["appliance_id"],
            "appliance_name": ap["name"],
            "brand": ap["brand"],
            "model": ap["model"],
            "task": task,
            "start_time": start_time_str,
            "duration_minutes": dur,
            "power_w": ap["rated_power_w"],
            "energy_kwh": round(energy, 3),
            "cost_yuan": cost,
            "noise_db": ap.get("noise_db", "N/A"),
        })

        # 递增：当前设备完成时间 + 30分钟缓冲
        next_start_hour = start_h + dur / 60.0 + 0.5

    # 对比峰电费用
    peak_total = round(total_cost * ELECTRICITY_PRICE["peak"]["price_per_kwh"] / ELECTRICITY_PRICE["valley"]["price_per_kwh"], 2)
    savings = round(peak_total - total_cost, 2)

    return {
        "date": target_date,
        "schedule": schedule,
        "total_devices": len(schedule),
        "total_energy_kwh": round(total_energy, 2),
        "total_cost_yuan_off_peak": round(total_cost, 2),
        "total_cost_yuan_if_peak": peak_total,
        "electricity_saved_yuan": savings,
        "electricity_saved_percent": round(savings / peak_total * 100, 1) if peak_total > 0 else 0,
        "price_note": f"谷电 {ELECTRICITY_PRICE['valley']['price_per_kwh']}元/度 vs 峰电 {ELECTRICITY_PRICE['peak']['price_per_kwh']}元/度",
    }


async def control_smart_appliance(
    user_id: str,
    appliance_id: str,
    action: str,
) -> dict:
    """控制智能家电 (模拟 IoT 指令)"""
    ap = next((a for a in REAL_APPLIANCES if a["appliance_id"] == appliance_id), None)
    if not ap:
        return {"error": f"家电不存在: {appliance_id}"}
    if not ap["is_smart"]:
        return {"error": f"{ap['name']} 不支持智能控制，请手动操作"}

    valid_actions = {
        "robot_vacuum": ["start", "pause", "resume", "dock", "status"],
        "washing_machine": ["start", "pause", "cancel", "status"],
        "dishwasher": ["start", "pause", "cancel", "status"],
        "air_conditioner": ["on", "off", "cool", "heat", "dry", "fan_only", "set_temp", "status"],
        "refrigerator": ["status", "fast_cool", "vacation_mode"],
    }
    ap_type = ap["appliance_type"]
    allowed = valid_actions.get(ap_type, ["on", "off", "status"])
    if action not in allowed:
        return {"error": f"不支持操作: {action}，{ap['name']} 支持: {allowed}"}

    return {
        "appliance_id": appliance_id,
        "appliance_name": ap["name"],
        "action": action,
        "status": "success",
        "message": f"{ap['name']}({ap['brand']} {ap['model']}) 已执行 {action} 操作",
        "timestamp": datetime.now().isoformat(),
    }
