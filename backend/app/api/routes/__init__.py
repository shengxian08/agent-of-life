"""
API 路由模块 v5.3
"""
from .agent import router as agent_router
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .database import router as database_router
from .knowledge import router as knowledge_router

routers = [
    auth_router, agent_router, dashboard_router, database_router, knowledge_router,
]
