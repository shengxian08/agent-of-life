"""
FastAPI 依赖注入 v5.2
"""
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


