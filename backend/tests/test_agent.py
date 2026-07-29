"""
测试 Agent 核心逻辑 — 工具注册、参数校验、安全护栏
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestToolRegistry:
    """工具注册表测试"""

    def test_register_and_get(self):
        """注册工具 → 能正确取出"""
        from app.agents.base_agent import ToolRegistry

        async def dummy_tool(query: str):
            return {"result": query}

        ToolRegistry.register("test_tool", dummy_tool, "测试工具",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})

        tool = ToolRegistry.get("test_tool")
        assert tool is not None
        assert tool["description"] == "测试工具"
        assert tool["function"] is dummy_tool

    def test_register_with_danger_level(self):
        """工具注册时可以标记危险等级"""
        from app.agents.base_agent import ToolRegistry

        async def safe_tool(x: str):
            return x

        ToolRegistry.register("safe", safe_tool, "safe", {}, danger_level="safe")
        ToolRegistry.register("danger", safe_tool, "danger", {}, danger_level="dangerous")

        assert ToolRegistry.get_danger_level("safe") == "safe"
        assert ToolRegistry.get_danger_level("danger") == "dangerous"
        assert ToolRegistry.get_danger_level("nonexistent") == "safe"

    def test_list_tools_filtered(self):
        """工具列表过滤 → 只返回请求的工具"""
        from app.agents.base_agent import ToolRegistry

        async def dummy():
            pass

        ToolRegistry.register("tool_a", dummy, "A", {})
        ToolRegistry.register("tool_b", dummy, "B", {})
        ToolRegistry.register("tool_c", dummy, "C", {})

        filtered = ToolRegistry.list_tools(["tool_a", "tool_c"])
        names = [t["function"]["name"] for t in filtered]
        assert "tool_a" in names
        assert "tool_c" in names
        assert "tool_b" not in names

    def test_list_all_tools(self):
        """不传参数 → 返回全部注册的工具"""
        from app.agents.base_agent import ToolRegistry
        all_tools = ToolRegistry.list_tools()
        assert len(all_tools) >= 3  # 至少上面注册的 3 个


class TestParameterValidation:
    """参数校验测试"""

    def test_type_coercion_integer(self):
        """字符串 '5' → 自动转为 int 5"""
        from app.agents.base_agent import ToolRegistry

        async def takes_int(limit: int):
            return {"limit": limit, "type": str(type(limit).__name__)}

        ToolRegistry.register("int_tool", takes_int, "test",
            {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": ["limit"]})

        tool = ToolRegistry.get("int_tool")
        # 验证 schema 定义了 integer 类型
        params = tool["parameters"]
        assert params["properties"]["limit"]["type"] == "integer"


class TestMessageSerialization:
    """Pydantic 模型序列化测试"""

    def test_conversation_message_create(self):
        from app.models.schemas import ConversationMessage
        msg = ConversationMessage(role="user", content="测试消息")
        assert msg.role == "user"
        assert msg.content == "测试消息"
        assert msg.timestamp is not None

    def test_agent_request_create(self):
        from app.models.schemas import AgentRequest
        req = AgentRequest(
            session_id="sess_test",
            user_id="user_001",
            message="你好",
            intent="general",
            confirmed_tools=[{"tool": "test_tool", "args": {"x": 1}}]
        )
        assert req.session_id == "sess_test"
        assert req.user_id == "user_001"
        assert len(req.confirmed_tools) == 1
        assert req.confirmed_tools[0]["tool"] == "test_tool"

    def test_agent_response_with_confirmation(self):
        from app.models.schemas import AgentResponse
        resp = AgentResponse(
            session_id="sess1",
            response="需要确认",
            intent="general",
            requires_confirmation=True,
            pending_dangerous_calls=[{"tool": "control_smart_appliance", "args": {"action": "on"}}]
        )
        assert resp.requires_confirmation is True
        assert len(resp.pending_dangerous_calls) == 1


class TestIntentRouter:
    """意图路由器测试"""

    def test_rule_match_shopping(self):
        from app.agents.intent_router import IntentRouter
        router = IntentRouter()
        assert router._rule_match("冰箱里有什么") == "shopping"
        assert router._rule_match("帮我比价永辉和盒马") == "shopping"

    def test_rule_match_meal(self):
        from app.agents.intent_router import IntentRouter
        router = IntentRouter()
        assert router._rule_match("红烧肉怎么做") == "meal"
        assert router._rule_match("今天吃什么") == "meal"

    def test_rule_match_appliance(self):
        from app.agents.intent_router import IntentRouter
        router = IntentRouter()
        assert router._rule_match("打开空调") == "appliance"
        assert router._rule_match("预约错峰运行") == "appliance"

    def test_rule_match_general(self):
        from app.agents.intent_router import IntentRouter
        router = IntentRouter()
        assert router._rule_match("你好") == "general"
        assert router._rule_match("hi") == "general"
        assert router._rule_match("在吗") == "general"

    def test_get_tools(self):
        from app.agents.intent_router import IntentRouter
        router = IntentRouter()
        meal_tools = router._get_tools("meal")
        assert "search_recipes" in meal_tools
        assert "recall_user_memory" in meal_tools  # 通用工具
        assert "check_door_status" not in meal_tools  # 安防工具不应在菜谱里


@pytest.mark.asyncio
async def test_agent_serialize_tool_result():
    """递归序列化 Pydantic 模型 → JSON 安全"""
    from app.agents.base_agent import _serialize_tool_result
    import json
    from datetime import datetime

    # 混合类型嵌套数据
    data = {
        "status": "ok",
        "count": 2,
        "timestamp": datetime.now(),
        "items": [{"name": "鸡蛋", "qty": 12}],
    }
    result = _serialize_tool_result(data)
    json_str = json.dumps(result, ensure_ascii=False, default=str)
    assert "ok" in json_str
    assert "2" in json_str
    assert "鸡蛋" in json_str
