"""
数据库浏览 + 完整 CRUD API
"""
from fastapi import APIRouter, Query, Body, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime

from ...models.database import get_db, User, FridgeItem, ShoppingRecord, MealPlanRecord, ApplianceRecord, MaintenanceRecord, FeedbackRecord
from .auth import get_current_user

router = APIRouter(prefix="/db", tags=["Database"])

async def _ensure_user_exists(user_id: str):
    """自动创建用户记录（游客首次操作时），如果已存在则跳过"""
    from sqlalchemy import select
    async for session in get_db():
        existing = (await session.execute(
            select(User).where(User.user_id == user_id)
        )).scalar_one_or_none()
        if existing:
            return
        session.add(User(
            user_id=user_id,
            name=user_id.replace("guest_", "游客"),
            family_size=1,
        ))
        await session.commit()

MODELS = {
    "users": (User, ["user_id","name","email","family_size","dietary_preferences","allergies","budget_monthly","city","password_hash","created_at","last_login"]),
    "fridge": (FridgeItem, ["item_id","user_id","name","category","quantity","unit","expiry_date","storage_location","price"]),
    "appliances": (ApplianceRecord, ["appliance_id","user_id","name","appliance_type","brand","model","purchase_date","warranty_expiry","maintenance_cycle_days"]),
    "shopping": (ShoppingRecord, ["record_id","user_id","supermarket","total_cost","purchased_at"]),
    "meal_plans": (MealPlanRecord, ["plan_id","user_id","start_date","end_date","generated_at"]),
    "maintenance": (MaintenanceRecord, ["task_id","user_id","appliance_name","task_type","priority","status","due_date","estimated_cost"]),
    "feedback": (FeedbackRecord, ["feedback_id","user_id","session_id","rating","comment","user_message","agent_response","created_at"]),
}


class InsertFridgeItem(BaseModel):
    user_id: str = Field(default="user_001")
    name: str
    category: str = Field(default="其他")
    quantity: float = Field(default=1.0, ge=0.01)
    unit: str = Field(default="个")
    expiry_days: int = Field(default=7, ge=0)
    storage_location: str = Field(default="冰箱冷藏")
    price: float = Field(default=0.0, ge=0)


class UpdateFridgeItem(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    storage_location: Optional[str] = None
    expiry_days: Optional[int] = None
    price: Optional[float] = None


class InsertAppliance(BaseModel):
    user_id: str = Field(default="user_001")
    name: str
    appliance_type: str = Field(default="other")
    brand: str = ""
    model: str = ""
    maintenance_cycle_days: int = Field(default=180, ge=1)


class InsertMaintenance(BaseModel):
    user_id: str = Field(default="user_001")
    appliance_id: str
    appliance_name: str
    task_type: str = Field(default="cleaning")
    description: str = ""
    priority: str = Field(default="medium")
    due_date: Optional[str] = None
    estimated_cost: float = Field(default=0.0, ge=0)


class InsertUser(BaseModel):
    user_id: str
    name: str
    family_size: int = Field(default=1, ge=1, le=20)
    dietary_preferences: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    budget_monthly: float = Field(default=3000.0, ge=0)


# ============================================================
# 📊 总览
# ============================================================

@router.get("/_overview")
async def db_overview():
    """一次性查看所有表的数据量"""
    from sqlalchemy import select, func
    overview = {}
    total = 0
    async for session in get_db():
        for name, (model, _) in MODELS.items():
            result = await session.execute(select(func.count()).select_from(model))
            count = result.scalar() or 0
            overview[name] = count
            total += count
    return {"total_rows": total, "tables": overview}


# ============================================================
# 🔍 查看
# ============================================================

@router.get("/tables")
async def list_tables():
    return {"tables": list(MODELS.keys()), "hint": "用 GET /db/{table_name} 查看具体数据"}


@router.get("/{table_name}")
async def browse_table(
    table_name: str,
    limit: int = Query(50, ge=1, le=200, description="返回行数"),
    user_id: str = Query("", description="按用户ID过滤（留空=全部）"),
):
    """浏览指定表的数据，支持按 user_id 过滤"""
    if table_name not in MODELS:
        return {"error": f"Unknown table. Available: {list(MODELS.keys())}"}
    model, cols = MODELS[table_name]
    async for session in get_db():
        from sqlalchemy import select
        stmt = select(model)
        if user_id and hasattr(model, "user_id"):
            stmt = stmt.where(model.user_id == user_id)
        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        data = []
        for row in rows:
            item = {}
            for col in cols:
                val = getattr(row, col, None)
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                item[col] = val
            data.append(item)
        return {
            "table": table_name,
            "filter": f"user_id={user_id}" if user_id else "全部",
            "count": len(data),
            "columns": cols,
            "rows": data,
        }


# ============================================================
# 🛒 冰箱食材 — 完整 CRUD
# ============================================================

@router.post("/fridge/insert", summary="添加食材到冰箱")
async def insert_fridge_item(data: InsertFridgeItem, user_id: str = Depends(get_current_user)):
    """插入一条冰箱食材，同名自动累加数量"""
    data.user_id = user_id  # JWT 身份覆盖，防止伪造
    await _ensure_user_exists(user_id)  # 自动创建游客用户
    from datetime import date as dt_date, timedelta
    async for session in get_db():
        from sqlalchemy import select
        existing = (await session.execute(
            select(FridgeItem).where(
                FridgeItem.user_id == data.user_id,
                FridgeItem.name == data.name
            )
        )).scalar_one_or_none()

        if existing:
            existing.quantity += data.quantity
            await session.commit()
            return {"status": "updated", "name": data.name, "new_quantity": existing.quantity}

        item_id = f"fi_{datetime.now().timestamp():.0f}"
        expiry = dt_date.today() + timedelta(days=data.expiry_days)
        session.add(FridgeItem(
            item_id=item_id, user_id=data.user_id, name=data.name,
            category=data.category, quantity=data.quantity, unit=data.unit,
            purchase_date=dt_date.today(), expiry_date=expiry,
            storage_location=data.storage_location, price=data.price,
        ))
        await session.commit()
        return {"status": "inserted", "name": data.name, "expiry_date": expiry.isoformat()}


@router.put("/fridge/update", summary="修改冰箱食材")
async def update_fridge_item(item_id: str = Body(...), data: UpdateFridgeItem = Body(...), user_id: str = Depends(get_current_user)):
    """修改食材的数量、位置、过期天数等"""
    from datetime import date as dt_date, timedelta
    async for session in get_db():
        from sqlalchemy import select
        item = (await session.execute(
            select(FridgeItem).where(FridgeItem.item_id == item_id)
        )).scalar_one_or_none()
        if not item:
            return {"error": "Item not found"}

        changed = []
        if data.quantity is not None:
            item.quantity = data.quantity; changed.append("quantity")
        if data.unit is not None:
            item.unit = data.unit; changed.append("unit")
        if data.category is not None:
            item.category = data.category; changed.append("category")
        if data.storage_location is not None:
            item.storage_location = data.storage_location; changed.append("storage_location")
        if data.expiry_days is not None:
            item.expiry_date = dt_date.today() + timedelta(days=data.expiry_days)
            changed.append("expiry_date")
        if data.price is not None:
            item.price = data.price; changed.append("price")

        await session.commit()
        return {"status": "updated", "item_id": item_id, "changed_fields": changed}


@router.post("/fridge/delete", summary="删除冰箱食材")
async def delete_fridge_item(item_id: str = Body(...), auth_user: str = Depends(get_current_user)):
    """删除一条冰箱食材"""
    async for session in get_db():
        from sqlalchemy import select
        item = (await session.execute(
            select(FridgeItem).where(FridgeItem.item_id == item_id)
        )).scalar_one_or_none()
        if not item:
            return {"error": "Item not found"}
        await session.delete(item)
        await session.commit()
        return {"status": "deleted", "name": item.name}


# ============================================================
# 🔌 家电 — 完整 CRUD
# ============================================================

@router.post("/appliances/insert", summary="添加家电")
async def insert_appliance(data: InsertAppliance, user_id: str = Depends(get_current_user)):
    """插入一台家电"""
    data.user_id = user_id  # JWT 身份覆盖
    await _ensure_user_exists(user_id)
    async for session in get_db():
        aid = f"ap_{datetime.now().timestamp():.0f}"
        session.add(ApplianceRecord(
            appliance_id=aid, user_id=data.user_id, name=data.name,
            appliance_type=data.appliance_type, brand=data.brand, model=data.model,
            maintenance_cycle_days=data.maintenance_cycle_days,
            purchase_date=date.today(),
        ))
        await session.commit()
        return {"status": "inserted", "appliance_id": aid, "name": data.name}


@router.post("/appliances/delete", summary="删除家电")
async def delete_appliance(appliance_id: str = Body(...), auth_user: str = Depends(get_current_user)):
    """删除一台家电"""
    async for session in get_db():
        from sqlalchemy import select
        item = (await session.execute(
            select(ApplianceRecord).where(ApplianceRecord.appliance_id == appliance_id)
        )).scalar_one_or_none()
        if not item:
            return {"error": "Appliance not found"}
        await session.delete(item)
        await session.commit()
        return {"status": "deleted", "name": item.name}


# ============================================================
# 🔧 维保 — 完整 CRUD
# ============================================================

@router.post("/maintenance/insert", summary="添加维保任务")
async def insert_maintenance(data: InsertMaintenance, user_id: str = Depends(get_current_user)):
    """插入一条维保任务"""
    data.user_id = user_id  # JWT 身份覆盖
    await _ensure_user_exists(user_id)
    async for session in get_db():
        task_id = f"mt_{datetime.now().timestamp():.0f}"
        due = date.fromisoformat(data.due_date) if data.due_date else date.today()
        session.add(MaintenanceRecord(
            task_id=task_id, user_id=data.user_id,
            appliance_id=data.appliance_id, appliance_name=data.appliance_name,
            task_type=data.task_type, description=data.description,
            priority=data.priority, status="pending",
            due_date=due, estimated_cost=data.estimated_cost,
        ))
        await session.commit()
        return {"status": "inserted", "task_id": task_id}


@router.post("/maintenance/delete", summary="删除维保任务")
async def delete_maintenance(task_id: str = Body(...), auth_user: str = Depends(get_current_user)):
    """删除一条维保任务"""
    async for session in get_db():
        from sqlalchemy import select
        item = (await session.execute(
            select(MaintenanceRecord).where(MaintenanceRecord.task_id == task_id)
        )).scalar_one_or_none()
        if not item:
            return {"error": "Maintenance task not found"}
        await session.delete(item)
        await session.commit()
        return {"status": "deleted", "task_name": item.appliance_name}


@router.put("/maintenance/update", summary="更新维保任务状态")
async def update_maintenance(
    task_id: str = Body(...),
    status: str = Body(default="completed"),
    user_id: str = Depends(get_current_user),
):
    """更新维保任务状态 (pending/scheduled/completed/cancelled)"""
    async for session in get_db():
        from sqlalchemy import select
        item = (await session.execute(
            select(MaintenanceRecord).where(MaintenanceRecord.task_id == task_id)
        )).scalar_one_or_none()
        if not item:
            return {"error": "Maintenance task not found"}
        item.status = status
        if status == "completed":
            item.completed_at = datetime.now()
        await session.commit()
        return {"status": "updated", "task_id": task_id, "new_status": status}


# ============================================================
# 👤 用户
# ============================================================

@router.post("/users/create", summary="创建用户")
async def create_user(data: InsertUser, auth_user: str = Depends(get_current_user)):
    """快速创建一个用户（跳过密码，仅供开发测试）"""
    async for session in get_db():
        from sqlalchemy import select
        existing = (await session.execute(
            select(User).where(User.user_id == data.user_id)
        )).scalar_one_or_none()
        if existing:
            return {"status": "exists", "user_id": data.user_id, "hint": "用户已存在，无需重复创建"}

        session.add(User(
            user_id=data.user_id,
            name=data.name,
            family_size=data.family_size,
            dietary_preferences=data.dietary_preferences,
            allergies=data.allergies,
            budget_monthly=data.budget_monthly,
        ))
        await session.commit()
        return {"status": "created", "user_id": data.user_id, "name": data.name}


@router.post("/users/delete", summary="删除用户")
async def delete_user(user_id: str = Body(...), auth_user: str = Depends(get_current_user)):
    """删除用户及其关联的所有数据"""
    async for session in get_db():
        from sqlalchemy import select, delete
        # 删除关联数据
        for model in [FridgeItem, ShoppingRecord, MealPlanRecord, MaintenanceRecord, ApplianceRecord]:
            await session.execute(delete(model).where(model.user_id == user_id))
        user = (await session.execute(select(User).where(User.user_id == user_id))).scalar_one_or_none()
        if not user:
            return {"error": "User not found"}
        await session.delete(user)
        await session.commit()
        return {"status": "deleted", "user_id": user_id, "hint": "已级联删除该用户的所有关联数据"}
