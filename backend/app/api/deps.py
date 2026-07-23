"""
FastAPI 依赖注入 v5.2 — 新增 JWT 认证依赖
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials

from ..agents.crew import get_household_crew, HouseholdCrew
from ..memory.conversation_memory import get_conversation_memory, ConversationMemory
from ..memory.user_profile import get_profile_manager, UserProfileManager
from ..rag.qa_chain import get_rag_chain, RAGChain
from ..rag.retriever import get_retriever, HybridRetriever


async def get_crew() -> HouseholdCrew:
    """获取 Agent 战队"""
    return get_household_crew()


async def get_memory() -> ConversationMemory:
    """获取对话记忆"""
    return get_conversation_memory()


async def get_profile_mgr() -> UserProfileManager:
    """获取用户画像管理器"""
    return get_profile_manager()


async def get_rag() -> RAGChain:
    """获取 RAG 链"""
    return get_rag_chain()


async def get_retriever_dep() -> HybridRetriever:
    """获取混合检索器"""
    return get_retriever()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = None,
    x_user_id: str | None = None,
) -> str:
    """获取当前用户ID — 优先JWT，降级header，默认user_001"""
    try:
        from .routes.auth import get_current_user
        from fastapi import Header, Depends
        # 尝试解析 JWT
        return await get_current_user(credentials, x_user_id)
    except Exception:
        pass
    return "user_001"
