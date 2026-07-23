"""
对话记忆 v4.0 — Redis 双向持久化 + 自动摘要 + 长期记忆固化
支持：LRU 淘汰、上下文窗口、记忆压缩、偏好提取
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..models.schemas import ConversationMessage
from ..config import settings
from .vector_store import get_vector_store


class ConversationMemory:
    """对话记忆管理器 — 双层存储 (内存热缓存 + Redis 持久化)"""

    def __init__(self, max_history: int | None = None):
        self.max_history = max_history or settings.conversation_history_limit
        self._memory: dict[str, list[ConversationMessage]] = defaultdict(list)
        self._redis = None
        self._redis_connected = False
        self._summary_cache: dict[str, str] = {}
        # Simple semantic cache: {query_hash: (response, timestamp)}
        self._semantic_cache: dict[str, tuple[str, datetime]] = {}
        self._cache_ttl_seconds = 300  # 5 分钟 TTL

    async def _get_redis(self):
        """懒连接 Redis，带重试"""
        if not REDIS_AVAILABLE:
            return None
        if self._redis is not None:
            return self._redis

        try:
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                max_connections=settings.redis_max_connections,
            )
            await self._redis.ping()
            self._redis_connected = True
            logger.info("Redis connected for conversation memory")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), using in-memory fallback")
            self._redis = None
            self._redis_connected = False

        return self._redis

    # ================================================================
    # 消息写入（双写：内存 + Redis）
    # ================================================================

    async def add_message(self, session_id: str, message: ConversationMessage):
        """添加对话消息 — 内存 + Redis 双写"""
        # 内存写入
        self._memory[session_id].append(message)
        if len(self._memory[session_id]) > self.max_history:
            self._memory[session_id] = self._memory[session_id][-self.max_history:]

        # Redis 持久化
        r = await self._get_redis()
        if r:
            try:
                key = f"conv:{session_id}"
                pipe = r.pipeline()
                pipe.lpush(key, message.model_dump_json())
                pipe.ltrim(key, 0, self.max_history - 1)
                pipe.expire(key, 86400 * 7)  # 7 天 TTL
                await pipe.execute()
            except Exception as e:
                logger.debug(f"Redis write failed: {e}")

        # 自动触发记忆固化
        if len(self._memory[session_id]) >= settings.memory_consolidation_threshold:
            # 后台任务，不阻塞，带错误处理
            import asyncio
            async def _safe_consolidate():
                try:
                    await self._consolidate_if_needed(session_id)
                except Exception as e:
                    logger.debug(f"Background consolidation failed: {e}")
            asyncio.create_task(_safe_consolidate())

    # ================================================================
    # 消息读取（优先 Redis，降级内存）
    # ================================================================

    async def get_history(
        self, session_id: str, limit: int = 20
    ) -> list[ConversationMessage]:
        """获取对话历史 — 优先从 Redis 恢复"""
        # 优先使用内存缓存
        local = self._memory.get(session_id, [])
        if local:
            return local[-limit:]

        # 尝试从 Redis 恢复
        r = await self._get_redis()
        if r:
            try:
                key = f"conv:{session_id}"
                raw = await r.lrange(key, 0, limit - 1)
                if raw:
                    messages = []
                    for item in reversed(raw):  # lpush 是倒序存的
                        try:
                            data = json.loads(item)
                            messages.append(ConversationMessage(**data))
                        except Exception:
                            continue
                    # 恢复到内存缓存
                    self._memory[session_id] = messages
                    return messages[-limit:]
            except Exception as e:
                logger.debug(f"Redis read failed: {e}")

        return []

    async def get_context_window(
        self, session_id: str, window_size: int = 10
    ) -> list[dict[str, str]]:
        """获取 LLM 可用的上下文窗口 (openai message format)"""
        history = await self.get_history(session_id, limit=window_size)
        return [
            {"role": msg.role, "content": msg.content}
            for msg in history
            if msg.role in ("user", "assistant")
        ]

    # ================================================================
    # 记忆固化 — 自动摘要 + 偏好提取 + 长期存储
    # ================================================================

    async def _consolidate_if_needed(self, session_id: str):
        """检查是否需要固化记忆"""
        history = self._memory.get(session_id, [])
        if len(history) < settings.memory_consolidation_threshold:
            return

        # 检查是否最近已固化过（避免频繁固化）
        last_consolidation = self._summary_cache.get(f"last_cons_{session_id}")
        if last_consolidation:
            try:
                last_time = datetime.fromisoformat(last_consolidation)
                if datetime.now() - last_time < timedelta(minutes=5):
                    return
            except Exception:
                pass

        await self.summarize_and_store(session_id, "")

    async def summarize_and_store(self, session_id: str, user_id: str):
        """使用 LLM 总结对话并存入长期向量记忆"""
        history = self._memory.get(session_id, [])
        if len(history) < 4:
            return

        # 构建对话文本
        dialog_text = ""
        for msg in history[-10:]:
            role_name = "用户" if msg.role == "user" else "助手"
            dialog_text += f"{role_name}: {msg.content[:300]}\n"

        if not dialog_text.strip():
            return

        # 用 LLM 生成结构化摘要 + 偏好提取
        summary = await self._llm_summarize(dialog_text, user_id)

        # 存入向量库（长期记忆）
        try:
            vs = get_vector_store()
            await vs.add(
                texts=[summary],
                metadatas=[{
                    "user_id": user_id or session_id,
                    "session_id": session_id,
                    "type": "memory_consolidation",
                    "timestamp": datetime.now().isoformat(),
                    "ttl_days": settings.memory_long_term_ttl_days,
                }],
            )
            self._summary_cache[f"last_cons_{session_id}"] = datetime.now().isoformat()
            logger.debug(f"Memory consolidated for session {session_id}")
        except Exception as e:
            logger.warning(f"Memory consolidation failed: {e}")

    async def _llm_summarize(self, dialog_text: str, user_id: str) -> str:
        """调用 LLM 生成记忆摘要 + 偏好提取"""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.openai_base_url,
            )
            resp = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是记忆提取助手。从以下对话中提取关键信息，格式：\n"
                        "1. 用户偏好/习惯\n2. 重要事实/事件\n3. 待办事项\n"
                        "用简洁中文，不超过 150 字。"
                    ),
                }, {
                    "role": "user",
                    "content": f"对话记录：\n{dialog_text[:1500]}",
                }],
                temperature=0.1,
                max_tokens=200,
            )
            return (
                f"[记忆摘要 | {datetime.now().strftime('%m/%d %H:%M')}] "
                f"{resp.choices[0].message.content or '对话记录'}"
            )
        except Exception:
            # LLM 不可用时用规则提取
            return (
                f"[记忆摘要] 用户进行了家务相关对话，"
                f"涉及内容：{dialog_text[:200].replace(chr(10), ' ')}"
            )

    # ================================================================
    # 记忆检索
    # ================================================================

    async def search_memory(
        self, query: str, user_id: str = "", top_k: int = 5
    ) -> list[str]:
        """搜索相关的长期记忆"""
        vs = get_vector_store()
        results = await vs.search(query, top_k=top_k)
        return [
            r.get("text", "") for r in results
            if r.get("metadata", {}).get("type") in (
                "memory_consolidation", "conversation_summary"
            )
        ]

    # ================================================================
    # Semantic Cache (basic, for frequently repeated queries)
    # ================================================================

    def _cache_key(self, session_id: str, query: str) -> str:
        """Generate simple cache key from session and normalized query"""
        import hashlib
        normalized = query.strip().lower()[:200]
        return hashlib.md5(f"{session_id}:{normalized}".encode()).hexdigest()

    async def cache_lookup(self, session_id: str, query: str) -> str | None:
        """Check if query is in semantic cache"""
        key = self._cache_key(session_id, query)
        cached = self._semantic_cache.get(key)
        if cached:
            response, timestamp = cached
            if (datetime.now() - timestamp).total_seconds() < self._cache_ttl_seconds:
                return response
            else:
                del self._semantic_cache[key]
        return None

    async def cache_store(self, session_id: str, query: str, response: str):
        """Store query→response in semantic cache"""
        key = self._cache_key(session_id, query)
        self._semantic_cache[key] = (response, datetime.now())
        # LRU eviction: keep max 500 entries
        if len(self._semantic_cache) > 500:
            oldest = min(self._semantic_cache, key=lambda k: self._semantic_cache[k][1])
            del self._semantic_cache[oldest]

    # ================================================================
    # 生命周期
    # ================================================================

    async def clear(self, session_id: str):
        """清除会话记忆"""
        self._memory.pop(session_id, None)
        self._summary_cache.pop(f"last_cons_{session_id}", None)

        r = await self._get_redis()
        if r:
            try:
                await r.delete(f"conv:{session_id}")
            except Exception:
                pass

    async def close(self):
        """关闭 Redis 连接"""
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None


# 全局单例
_conversation_memory: ConversationMemory | None = None


def get_conversation_memory() -> ConversationMemory:
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory()
    return _conversation_memory
