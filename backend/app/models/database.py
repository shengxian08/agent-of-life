"""
数据库层 - SQLAlchemy 异步 + PostgreSQL v5.2
新增: 用户密码认证、Agent执行追踪、用户反馈
"""
from __future__ import annotations

from datetime import date, datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Column, String, Integer, Float, Date, DateTime, Text,
    Enum as SAEnum, ForeignKey, JSON
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from ..config import settings


class Base(DeclarativeBase):
    pass


# ============================================================
# SQLAlchemy 模型
# ============================================================

class User(Base):
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(256), nullable=True)       # bcrypt hash, nullable for legacy
    email = Column(String(200), nullable=True)
    family_size = Column(Integer, default=1)
    dietary_preferences = Column(JSON, default=list)
    allergies = Column(JSON, default=list)
    disliked_foods = Column(JSON, default=list)
    budget_monthly = Column(Float, default=3000.0)
    preferred_supermarkets = Column(JSON, default=list)
    city = Column(String(50), default="北京")
    location = Column(String(100), default="朝阳区")
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)


class FridgeItem(Base):
    __tablename__ = "fridge_items"

    item_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    name = Column(String(120), nullable=False)
    category = Column(String(50))
    quantity = Column(Float, default=1.0)
    unit = Column(String(20), default="个")
    purchase_date = Column(Date, default=date.today)
    expiry_date = Column(Date, nullable=True)
    storage_location = Column(String(50), default="冰箱冷藏")
    price = Column(Float, default=0.0)
    calories_per_unit = Column(Float, default=0.0)
    protein_per_unit = Column(Float, default=0.0)
    fat_per_unit = Column(Float, default=0.0)
    carbs_per_unit = Column(Float, default=0.0)


class ShoppingRecord(Base):
    __tablename__ = "shopping_records"

    record_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    list_id = Column(String(64))
    supermarket = Column(String(100))
    total_cost = Column(Float, default=0.0)
    items = Column(JSON, default=list)
    purchased_at = Column(DateTime, default=datetime.now)


class MealPlanRecord(Base):
    __tablename__ = "meal_plans"

    plan_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    meals = Column(JSON, default=dict)
    generated_at = Column(DateTime, default=datetime.now)


class ApplianceRecord(Base):
    __tablename__ = "appliances"

    appliance_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    name = Column(String(100))
    appliance_type = Column(String(50))
    brand = Column(String(50), default="")
    model = Column(String(50), default="")
    purchase_date = Column(Date, nullable=True)
    warranty_expiry = Column(Date, nullable=True)
    maintenance_cycle_days = Column(Integer, default=180)
    is_smart = Column(Integer, default=0)
    off_peak_only = Column(Integer, default=1)


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_tasks"

    task_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    appliance_id = Column(String(64))
    appliance_name = Column(String(100))
    task_type = Column(String(50))
    description = Column(Text, default="")
    priority = Column(String(20), default="medium")
    status = Column(String(20), default="pending")
    due_date = Column(Date, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_cost = Column(Float, default=0.0)
    service_contact = Column(String(100), default="")
    notes = Column(Text, default="")


# ============================================================
# v5.2 新增: Agent 执行追踪 & 用户反馈
# ============================================================

class TraceRecord(Base):
    """Agent 执行全链路追踪 — 每一步 ReAct 循环 + 工具调用"""
    __tablename__ = "agent_traces"

    trace_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    agent_name = Column(String(64), default="unified")
    intent = Column(String(32), default="general")
    user_message = Column(Text, default="")
    iteration = Column(Integer, default=0)           # ReAct 循环第几轮
    step_type = Column(String(32), default="llm_call")  # llm_call / tool_call / tool_result / final
    detail = Column(JSON, default=dict)              # 具体内容(工具名/参数/结果摘要/token数)
    duration_ms = Column(Integer, default=0)         # 此步耗时
    created_at = Column(DateTime, default=datetime.now)


class FeedbackRecord(Base):
    """用户反馈 — 响应质量评价"""
    __tablename__ = "user_feedback"

    feedback_id = Column(String(64), primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(64), nullable=True)       # 关联的 trace
    user_message = Column(Text, default="")
    agent_response = Column(Text, default="")
    rating = Column(String(16), default="neutral")    # positive / negative / neutral
    comment = Column(Text, default="")                 # 用户补充说明
    created_at = Column(DateTime, default=datetime.now)


class TokenUsageRecord(Base):
    """LLM Token 用量追踪"""
    __tablename__ = "token_usage"

    record_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=False)
    model = Column(String(64), default="")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    estimated_cost_cny = Column(Float, default=0.0)    # 估算人民币费用
    endpoint = Column(String(128), default="")          # 调用的 API 端点
    created_at = Column(DateTime, default=datetime.now)


class TrackingNumber(Base):
    """用户录入的快递单号"""
    __tablename__ = "tracking_numbers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    tracking_id = Column(String(64), nullable=False)
    carrier = Column(String(32), default="顺丰")
    description = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.now)


# ============================================================
# 异步引擎 & 会话
# ============================================================
_engine = None
_async_session_maker = None


def _get_engine():
    global _engine, _async_session_maker
    if _engine is None:
        db_url = settings.database_url
        _engine = create_async_engine(
            db_url, echo=False, future=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
        )
        _async_session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def init_db():
    """初始化数据库表"""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """依赖注入：获取数据库会话"""
    if _async_session_maker is None:
        _get_engine()
    async with _async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
