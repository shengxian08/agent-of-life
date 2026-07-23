"""
Pydantic 数据模型 - 所有 API 数据的严格校验
"""
from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# 枚举类型
# ============================================================

class ApplianceType(str, Enum):
    ROBOT_VACUUM = "robot_vacuum"       # 扫地机器人
    WASHING_MACHINE = "washing_machine"  # 洗衣机
    DISHWASHER = "dishwasher"            # 洗碗机
    AIR_CONDITIONER = "air_conditioner"  # 空调
    WATER_HEATER = "water_heater"        # 热水器
    REFRIGERATOR = "refrigerator"        # 冰箱
    OVEN = "oven"                        # 烤箱
    OTHER = "other"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class ShoppingCategory(str, Enum):
    VEGETABLES = "蔬菜"
    FRUITS = "水果"
    MEAT = "肉类"
    SEAFOOD = "海鲜"
    DAIRY = "乳制品"
    GRAINS = "粮油"
    CONDIMENTS = "调味品"
    BEVERAGES = "饮品"
    SNACKS = "零食"
    HOUSEHOLD = "日用品"
    OTHER = "其他"


class MaintenanceStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================================
# 核心数据模型
# ============================================================

class UserProfile(BaseModel):
    """用户及家庭信息"""
    user_id: str
    name: str
    family_size: int = Field(default=1, ge=1, le=20)
    dietary_preferences: list[str] = Field(default_factory=list)  # 饮食偏好
    allergies: list[str] = Field(default_factory=list)            # 过敏物
    disliked_foods: list[str] = Field(default_factory=list)       # 不喜欢的食物
    budget_monthly: float = Field(default=3000.0, ge=0)           # 月度餐饮预算
    preferred_supermarkets: list[str] = Field(default_factory=list)  # 偏好超市
    city: str = Field(default="北京")
    location: str = Field(default="朝阳区")


class Household(BaseModel):
    """家庭信息"""
    household_id: str
    address: str
    members: list[UserProfile] = Field(default_factory=list)
    appliances: list[Appliance] = Field(default_factory=list)


class Appliance(BaseModel):
    """家电信息"""
    appliance_id: str
    name: str
    appliance_type: ApplianceType
    brand: str = ""
    model: str = ""
    purchase_date: Optional[date] = None
    warranty_expiry: Optional[date] = None
    last_maintenance: Optional[date] = None
    maintenance_cycle_days: int = Field(default=180, ge=1, le=3650)  # 维保周期
    is_smart: bool = Field(default=False)              # 是否智能家电
    off_peak_only: bool = Field(default=True)          # 是否仅错峰运行


class Ingredient(BaseModel):
    """食材"""
    ingredient_id: str
    name: str
    category: ShoppingCategory
    quantity: float = Field(default=0.0, ge=0)
    unit: str = Field(default="个")  # 个/斤/kg/袋/瓶
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    storage_location: str = Field(default="冰箱冷藏")  # 冰箱冷藏/冷冻/常温
    price: float = Field(default=0.0, ge=0)
    calories_per_unit: float = Field(default=0.0)
    protein_per_unit: float = Field(default=0.0)
    fat_per_unit: float = Field(default=0.0)
    carbs_per_unit: float = Field(default=0.0)


class Recipe(BaseModel):
    """菜谱"""
    recipe_id: str
    name: str
    cuisine: str = ""                    # 菜系
    meal_type: MealType = MealType.DINNER
    ingredients_required: list[dict[str, Any]] = Field(default_factory=list, max_items=50)
    cooking_time_minutes: int = Field(default=30, ge=1, le=1440)
    difficulty: int = Field(default=2, ge=1, le=5)
    calories_total: float = Field(default=500.0, ge=0, le=10000)
    instructions: list[str] = Field(default_factory=list, max_items=30)
    tags: list[str] = Field(default_factory=list, max_items=10)
    rating: float = Field(default=4.0, ge=0, le=5)
    image_url: str = ""


class ShoppingItem(BaseModel):
    """购物清单项"""
    item_id: str
    name: str
    category: ShoppingCategory
    quantity: float = Field(ge=0)
    unit: str = "个"
    estimated_price: float = Field(default=0.0, ge=0)
    is_urgent: bool = False
    notes: str = ""
    alternative: str = ""  # 替代品


class ShoppingList(BaseModel):
    """购物清单"""
    list_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    items: list[ShoppingItem] = Field(default_factory=list)
    total_estimated: float = Field(default=0.0)
    supermarket: str = ""
    status: str = "pending"  # pending / purchasing / completed


class MealPlan(BaseModel):
    """一周菜谱计划"""
    plan_id: str
    start_date: date
    end_date: date
    meals: dict[str, list[Recipe]] = Field(default_factory=dict)  # {"2026-07-20": [breakfast, lunch, dinner]}
    total_calories_daily: dict[str, float] = Field(default_factory=dict)
    generated_from_fridge: bool = Field(default=True)


class PriceComparison(BaseModel):
    """比价结果"""
    item_name: str
    supermarket: str
    price: float
    unit: str
    promotion: str = ""
    last_updated: datetime = Field(default_factory=datetime.now)
    source_url: str = ""


class MaintenanceTask(BaseModel):
    """维保任务"""
    task_id: str
    appliance_id: str
    appliance_name: str
    task_type: str  # cleaning / repair / inspection / replacement
    description: str
    priority: Priority = Priority.MEDIUM
    status: MaintenanceStatus = MaintenanceStatus.PENDING
    due_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    estimated_cost: float = Field(default=0.0)
    service_contact: str = ""      # 维修师傅电话
    notes: str = ""


# ============================================================
# Agent 通信模型
# ============================================================

class AgentRequest(BaseModel):
    """Agent 请求"""
    session_id: str
    user_id: str
    message: str
    intent: Optional[str] = None  # shopping/meal_plan/appliance/maintenance/security/household/general
    context: dict[str, Any] = Field(default_factory=dict)
    stream: bool = Field(default=False)


# ============================================================
# v5.0 新增模型：家庭成员 / 场景 / 隐私 / 任务队列
# ============================================================

class FamilyMember(BaseModel):
    """家庭成员"""
    member_id: str
    name: str
    role: str = "member"  # owner / member / elder / child
    dietary_preferences: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    schedule_pattern: str = ""  # 作息规律描述
    preferences: dict[str, int] = Field(default_factory=dict)  # 个性化参数 0-100
    avatar: str = "👤"


class MemberSwitchRequest(BaseModel):
    """成员切换请求"""
    user_id: str
    member_id: str


class PrivacyToggleRequest(BaseModel):
    """隐私模式切换"""
    user_id: str
    local_mode: bool = True  # True=本地模式, False=云端模式


class SceneTriggerRequest(BaseModel):
    """场景触发请求"""
    user_id: str
    scene: str  # morning / away / evening / movie / cleaning
    session_id: str = ""


class TaskQueueItem(BaseModel):
    """跨Agent任务队列项"""
    task_id: str
    from_agent: str
    to_agent: str
    description: str
    status: str = "pending"  # pending / running / done / failed
    created_at: datetime = Field(default_factory=datetime.now)


class AIBriefResponse(BaseModel):
    """全局AI简报"""
    shopping_alert: str = ""
    meal_suggestion: str = ""
    appliance_status: str = ""
    maintenance_alert: str = ""
    security_status: str = ""
    household_tasks: str = ""
    overall_summary: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)


class OverviewStatus(BaseModel):
    """家庭总览驾驶舱状态"""
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    active_tasks: int = 0
    today_interactions: int = 0
    system_status: str = "healthy"
    llm_service: str = "online"
    vector_service: str = "online"
    uptime: str = ""


class SecurityEvent(BaseModel):
    """安防事件"""
    event_id: str
    event_type: str  # visitor / motion / alarm / arm / disarm
    description: str
    level: str = "info"  # info / warning / alert
    timestamp: datetime = Field(default_factory=datetime.now)
    camera_id: str = ""
    snapshot_url: str = ""


class HouseholdTask(BaseModel):
    """家庭事务任务"""
    task_id: str
    task_type: str  # schedule / package / property / visitor
    title: str
    description: str
    due_date: Optional[date] = None
    status: str = "pending"
    assigned_member: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class AgentResponse(BaseModel):
    """Agent 响应"""
    session_id: str
    response: str
    intent: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================
# v5.2 新增: 认证 & 追踪 & 反馈
# ============================================================

class LoginRequest(BaseModel):
    """登录请求"""
    email: str = Field(default="", description="邮箱登录")
    username: str = Field(default="", description="用户名登录(兼容)")
    password: str = Field(..., min_length=4, max_length=128)


class RegisterRequest(BaseModel):
    """注册请求"""
    email: str = Field(..., min_length=3, max_length=200)
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)
    family_size: int = Field(default=1, ge=1, le=20)


class TokenResponse(BaseModel):
    """JWT 令牌响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    expires_in: int  # 秒


class TraceStep(BaseModel):
    """追踪步骤"""
    trace_id: str
    iteration: int
    step_type: str       # llm_call / tool_call / tool_result / final
    agent_name: str
    detail: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


class TraceSummary(BaseModel):
    """对话追踪摘要"""
    session_id: str
    user_message: str
    agent_response: str
    intent: str
    confidence: float
    total_duration_ms: int
    steps: list[TraceStep] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)   # {prompt, completion, total}
    tool_calls_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class FeedbackRequest(BaseModel):
    """用户反馈请求"""
    session_id: str
    user_message: str = ""
    agent_response: str = ""
    rating: str = "neutral"  # positive / negative / neutral
    comment: str = ""


class TokenStats(BaseModel):
    """Token 用量统计"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_cny: float = 0.0
    calls_count: int = 0
    by_model: dict[str, dict[str, int]] = Field(default_factory=dict)  # {model: {prompt, completion, total, cost}}


class ConversationMessage(BaseModel):
    """对话消息"""
    role: str  # user / assistant / system / tool
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(BaseModel):
    """记忆条目"""
    memory_id: str
    user_id: str
    content: str
    memory_type: str  # preference / event / fact / conversation
    embedding: Optional[list[float]] = None
    importance: float = Field(default=0.5, ge=0, le=1)
    created_at: datetime = Field(default_factory=datetime.now)
    last_accessed: datetime = Field(default_factory=datetime.now)
    access_count: int = Field(default=0)
