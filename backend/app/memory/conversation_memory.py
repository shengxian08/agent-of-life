"""
对话记忆 v4.0 — Redis 双向持久化 + 自动摘要 + 长期记忆固化
支持：LRU 淘汰、上下文窗口、记忆压缩、偏好提取
"""
from __future__ import annotations

import asyncio
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
        self._session_users: dict[str, str] = {}  # session_id → user_id 映射

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

    async def add_message(self, session_id: str, message: ConversationMessage,
                          user_id: str = ""):
        """添加对话消息 — 内存 + Redis 双写"""
        # 记录 session → user 映射（用于记忆固化时关联用户）
        if user_id:
            self._session_users[session_id] = user_id

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

        user_id = self._session_users.get(session_id, "")
        await self.summarize_and_store(session_id, user_id)

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
    # 记忆检索（主入口）
    # ================================================================

    async def retrieve_user_memories(
        self, user_id: str, query: str = "", top_k: int = 10
    ) -> list[dict[str, Any]]:
        """检索用户所有跨会话的长期记忆（按相关度排序）

        这是记忆系统被 Agent 调用的主入口。搜索该用户所有已固化的对话摘要，
        支持按 query 做语义搜索，query 为空时返回最近记忆。
        """
        vs = get_vector_store()
        search_query = query or f"用户偏好 重要事实 待办事项 {user_id}"
        results = await vs.search(search_query, top_k=top_k)

        memories = []
        for r in results:
            meta = r.get("metadata", {})
            mem_user_id = meta.get("user_id", "")
            mem_type = meta.get("type", "")

            # 匹配该用户的记忆（或 session_id 包含 user_id）
            if mem_user_id == user_id or user_id in meta.get("session_id", ""):
                memories.append({
                    "text": r.get("text", ""),
                    "score": r.get("score", 0),
                    "timestamp": meta.get("timestamp", ""),
                    "session_id": meta.get("session_id", ""),
                    "type": mem_type,
                })

        # 按分数降序，分数相同时按时间降序
        memories.sort(key=lambda m: (m["score"], m.get("timestamp", "")), reverse=True)
        return memories[:top_k]

    async def retrieve_user_summary(self, user_id: str) -> str:
        """生成用户记忆总览（Agent 启动时注入 system prompt）"""
        memories = await self.retrieve_user_memories(user_id, top_k=8)
        if not memories:
            return ""

        lines = ["## 用户长期记忆（跨会话）"]
        for i, m in enumerate(memories):
            text = m["text"][:200]  # 每条摘要截断
            ts = m.get("timestamp", "")[:10] if m.get("timestamp") else "未知"
            lines.append(f"{i+1}. [{ts}] {text}")

        return "\n".join(lines)

    async def extract_and_update_preferences(
        self, user_id: str, dialog_text: str,
    ) -> dict[str, Any] | None:
        """从对话中自动提取偏好变化并写回用户画像

        用 LLM 分析对话，检测用户是否表达了新的口味偏好、过敏物、忌口、
        预算偏好等。如果检测到变化，自动调用 UserProfileManager 更新。
        """
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.openai_base_url,
                timeout=10.0,
            )
            resp = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是用户偏好提取助手。分析以下对话，提取用户表达的新偏好变化。\n"
                        "只提取明确表达了'改变/现在/已经/最近/不'等变化信号的内容，不要提取既有的静态描述。\n"
                        "返回 JSON 格式，没有变化时返回空对象 {}：\n"
                        '{\n'
                        '  "preferences": ["新增的口味偏好"],\n'
                        '  "allergies": ["新增的过敏物"],\n'
                        '  "disliked": ["新增的忌口"],\n'
                        '  "budget": 金额或null,\n'
                        '  "summary": "一句话总结变化"\n'
                        '}'
                    ),
                }, {
                    "role": "user",
                    "content": dialog_text[:2000],
                }],
                temperature=0.1,
                max_tokens=300,
            )
            content = resp.choices[0].message.content or "{}"

            # 尽量提取 JSON
            import json
            # 处理可能的 markdown 包裹
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content.strip())

            if not result or not isinstance(result, dict):
                return None

            # 检查是否有实际变化
            has_change = any([
                result.get("preferences"),
                result.get("allergies"),
                result.get("disliked"),
                result.get("budget"),
            ])
            if not has_change:
                return None

            # 写回用户画像
            if any([result.get("preferences"), result.get("allergies"), result.get("disliked")]):
                from .user_profile import get_profile_manager
                pm = get_profile_manager()
                await pm.update_preferences(
                    user_id=user_id,
                    preferences=result.get("preferences"),
                    allergies=result.get("allergies"),
                    disliked=result.get("disliked"),
                )

            logger.info(
                f"Auto preference update for {user_id}: {result.get('summary', 'changes detected')}"
            )
            return result

        except json.JSONDecodeError:
            logger.debug(f"Preference extraction: LLM returned non-JSON: {content[:100]}")
            return None
        except Exception as e:
            logger.debug(f"Preference extraction failed: {e}")
            return None

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