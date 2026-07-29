"""
测试对话记忆系统 — 纯内存测试，不依赖 Redis
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestConversationMemory:
    """对话记忆核心逻辑测试"""

    @pytest.fixture
    def memory(self):
        """创建纯内存实例（Redis 不可用时自动降级）"""
        from app.memory.conversation_memory import ConversationMemory
        return ConversationMemory(max_history=20)

    @pytest.fixture
    def msg(self):
        from app.models.schemas import ConversationMessage
        return ConversationMessage

    def test_add_and_retrieve(self, memory, msg):
        """写入消息 → 能正确读回"""
        import asyncio
        async def run():
            await memory.add_message("sess1", msg(role="user", content="你好"), user_id="u1")
            await memory.add_message("sess1", msg(role="assistant", content="你好！"), user_id="u1")
            history = await memory.get_history("sess1")
            assert len(history) == 2
            assert history[0].role == "user"
            assert history[0].content == "你好"
            assert history[1].role == "assistant"
        asyncio.run(run())

    def test_empty_history(self, memory):
        """空会话 → 返回空列表"""
        import asyncio
        async def run():
            history = await memory.get_history("nonexistent")
            assert history == []
        asyncio.run(run())

    def test_session_isolation(self, memory, msg):
        """不同 session 互不干扰"""
        import asyncio
        async def run():
            await memory.add_message("sess_a", msg(role="user", content="A的消息"), user_id="u1")
            await memory.add_message("sess_b", msg(role="user", content="B的消息"), user_id="u2")
            hist_a = await memory.get_history("sess_a")
            hist_b = await memory.get_history("sess_b")
            assert len(hist_a) == 1
            assert len(hist_b) == 1
            assert hist_a[0].content == "A的消息"
            assert hist_b[0].content == "B的消息"
        asyncio.run(run())

    def test_lru_eviction(self, memory, msg):
        """超过 max_history → 旧消息被淘汰"""
        import asyncio
        memory.max_history = 5
        async def run():
            for i in range(10):
                await memory.add_message("sess1", msg(role="user", content=f"消息{i}"), user_id="u1")
            history = await memory.get_history("sess1")
            assert len(history) <= 5
            # 应该保留最新的 5 条
            assert "消息9" in history[-1].content
            assert "消息0" not in [h.content for h in history]
        asyncio.run(run())

    def test_clear_session(self, memory, msg):
        """清除会话 → 历史为空"""
        import asyncio
        async def run():
            await memory.add_message("sess1", msg(role="user", content="test"), user_id="u1")
            await memory.clear("sess1")
            history = await memory.get_history("sess1")
            assert history == []
        asyncio.run(run())

    def test_semantic_cache(self, memory):
        """语义缓存 → 重复查询命中"""
        import asyncio
        async def run():
            await memory.cache_store("sess1", "红烧肉怎么做", "五花肉焯水后炖50分钟")
            cached = await memory.cache_lookup("sess1", "红烧肉怎么做")
            assert cached == "五花肉焯水后炖50分钟"
            # 不同 session 不命中
            not_cached = await memory.cache_lookup("sess2", "红烧肉怎么做")
            assert not_cached is None
        asyncio.run(run())

    def test_context_window(self, memory, msg):
        """获取 LLM 格式的上下文窗口"""
        import asyncio
        async def run():
            await memory.add_message("sess1", msg(role="user", content="问题1"), user_id="u1")
            await memory.add_message("sess1", msg(role="assistant", content="回答1"), user_id="u1")
            window = await memory.get_context_window("sess1", window_size=2)
            assert len(window) == 2
            assert window[0] == {"role": "user", "content": "问题1"}
            assert window[1] == {"role": "assistant", "content": "回答1"}
        asyncio.run(run())
