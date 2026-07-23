"""
API 路由模块 v5.2
"""
from .agent import router as agent_router
from .auth import router as auth_router
from .shopping import router as shopping_router
from .meal_plan import router as meal_plan_router
from .appliance import router as appliance_router
from .maintenance import router as maintenance_router
from .knowledge import router as knowledge_router
from .dashboard import router as dashboard_router
from .database import router as database_router
from .household_api import router as household_router

routers = [
    auth_router, agent_router, shopping_router, meal_plan_router,
    appliance_router, maintenance_router, knowledge_router,
    dashboard_router, database_router, household_router,
]
