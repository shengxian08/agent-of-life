"""
数据库浏览 + 插入 API
"""
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime

from ...models.database import get_db, User, FridgeItem, ShoppingRecord, MealPlanRecord, ApplianceRecord, MaintenanceRecord

router = APIRouter(prefix="/db", tags=["Database"])

MODELS = {
    "users": (User, ["user_id","name","family_size","dietary_preferences","allergies","budget_monthly","city"]),
    "fridge": (FridgeItem, ["item_id","user_id","name","category","quantity","unit","expiry_date","storage_location","price"]),
    "appliances": (ApplianceRecord, ["appliance_id","user_id","name","appliance_type","brand","model","purchase_date","warranty_expiry","maintenance_cycle_days"]),
    "shopping": (ShoppingRecord, ["record_id","user_id","supermarket","total_cost","purchased_at"]),
    "meal_plans": (MealPlanRecord, ["plan_id","user_id","start_date","end_date","generated_at"]),
    "maintenance": (MaintenanceRecord, ["task_id","user_id","appliance_name","task_type","priority","status","due_date","estimated_cost"]),
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


@router.get("/tables")
async def list_tables():
    return {"tables": list(MODELS.keys())}


@router.get("/{table_name}")
async def browse_table(table_name: str, limit: int = Query(50, ge=1, le=200)):
    if table_name not in MODELS:
        return {"error": f"Unknown table. Available: {list(MODELS.keys())}"}
    model, cols = MODELS[table_name]
    async for session in get_db():
        from sqlalchemy import select
        result = await session.execute(select(model).limit(limit))
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
        return {"table": table_name, "count": len(data), "columns": cols, "rows": data}


# ============================================================
# 插入 API
# ============================================================

@router.post("/fridge/insert")
async def insert_fridge_item(data: InsertFridgeItem):
    """插入一条冰箱食材"""
    from datetime import date as dt_date, timedelta
    async for session in get_db():
        from sqlalchemy import select
        # Check existing
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


@router.post("/fridge/delete")
async def delete_fridge_item(item_id: str = Body(...), user_id: str = Body(default="user_001")):
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


@router.post("/appliances/insert")
async def insert_appliance(data: InsertAppliance):
    """插入一台家电"""
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


@router.post("/maintenance/insert")
async def insert_maintenance(data: InsertMaintenance):
    """插入一条维保任务"""
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
