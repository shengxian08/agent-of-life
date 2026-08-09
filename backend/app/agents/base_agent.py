"""
Agent 基类 v5.2 — ReAct Agent + Function Calling + 全链路追踪 + 重试 + Token统计
新增: 执行追踪、工具重试(3次)、超时控制(30s)、Token用量记录
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Any, Callable, AsyncGenerator

from openai import AsyncOpenAI
from loguru import logger

from ..models.schemas import AgentRequest, AgentResponse
from ..config import settings

# Token 价格 (元/百万tokens) — DeepSeek 官方价格
TOKEN_PRICES = {
    "deepseek-chat": {"prompt": 1.0, "completion": 2.0},
    "deepseek-reasoner": {"prompt": 4.0, "completion": 16.0},
    "gpt-4o": {"prompt": 18.0, "completion": 54.0},
    "gpt-4o-mini": {"prompt": 1.0, "completion": 3.0},
    "default": {"prompt": 1.0, "completion": 2.0},
}

# 请求级视频卡片隔离（contextvars 确保并发请求互不干扰）
_video_html_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "stream_video_html", default=""
)

def get_pending_video_html() -> str:
    """读取当前请求的视频卡片 HTML（供路由层使用）"""
    return _video_html_var.get()

def clear_pending_video_html() -> None:
    """清除当前请求的视频卡片 HTML"""
    _video_html_var.set("")


class ToolRegistry:
    """工具注册表 — 全局单例

    danger_level 说明:
    - "safe": 纯读取操作，无需确认（如查询库存、检索菜谱）
    - "caution": 写入操作但不影响安全（如添加食材、创建任务）
    - "dangerous": 影响物理世界或安全的操作（如开关家电、布防撤防），需要用户确认
    """
    _tools: dict[str, dict] = {}

    @classmethod
    def register(cls, name: str, func: Callable, description: str, parameters: dict,
                 danger_level: str = "safe"):
        cls._tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
            "danger_level": danger_level,
        }

    @classmethod
    def get(cls, name: str) -> dict | None:
        return cls._tools.get(name)

    @classmethod
    def get_all(cls) -> dict:
        return cls._tools

    @classmethod
    def get_danger_level(cls, name: str) -> str:
        tool = cls._tools.get(name)
        return tool.get("danger_level", "safe") if tool else "safe"

    @classmethod
    def list_tools(cls, names: list[str] | None = None) -> list[dict]:
        result = []
        for name, info in cls._tools.items():
            if names is None or name in names:
                result.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        "parameters": info["parameters"],
                    }
                })
        return result


def _serialize_tool_result(obj: Any) -> Any:
    """递归序列化工具返回结果，将 Pydantic 模型转为 dict，确保 JSON 可序列化"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize_tool_result(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize_tool_result(v) for k, v in obj.items()}
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    return obj


def _make_confirmed_key(tool_name: str, args: dict, confirmed_set: set[str]) -> str:
    """生成确认键并检查是否在已确认集合中

    Returns:
        "{tool_name}:{args_hash}" 如果已确认，否则 ""
    """
    args_hash = hashlib.md5(
        json.dumps(args, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:8]
    key = f"{tool_name}:{args_hash}"
    return key if key in confirmed_set else ""


class BaseAgent:
    """ReAct Agent v2 — 改进版 ReAct 循环 + 并行工具调用"""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.tool_names = tools or []
        self.max_iterations = settings.agent_max_iterations
        self._client: AsyncOpenAI | None = None
        # 记忆系统：缓存用户长期记忆，首条消息时自动注入
        self._memory_injected: set[str] = set()
        self._last_preference_extraction: dict[str, float] = {}

    def _build_full_prompt(
        self,
        user_id: str,
        profile: dict | None = None,
        memory_context: str = "",
    ) -> str:
        """构建完整 System Prompt — run/run_stream 共享，确保行为一致"""
        parts = [self.system_prompt, ""]

        # 用户档案
        if profile:
            profile_parts = []
            if profile.get("name"):
                profile_parts.append(f"用户姓名: {profile['name']}")
            profile_parts.append(f"家庭成员: {profile.get('family_size', '')}人")
            if profile.get("dietary_preferences"):
                profile_parts.append(f"饮食偏好: {', '.join(profile['dietary_preferences'])}")
            if profile.get("allergies"):
                profile_parts.append(f"过敏物: {', '.join(profile['allergies'])}")
            if profile.get("disliked_foods"):
                profile_parts.append(f"忌口: {', '.join(profile['disliked_foods'])}")
            if profile.get("budget_monthly"):
                profile_parts.append(f"月度预算: {profile['budget_monthly']}元")
            parts.append(f"[用户档案] {' | '.join(profile_parts)}")

        # 基础上下文
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        parts.append(f"用户ID: {user_id} | 当前时间: {now}")

        # 记忆上下文
        if memory_context:
            parts.append(f"\n{memory_context}")

        # 行为约束（之前 run() 有但 run_stream() 漏掉的）
        parts.extend([
            "",
            "优先调用工具获取实时数据再回答，同一工具可多次调用（参数不同时）。",
            "回复：口语化中文，Markdown 层级排板。禁止面部表情 emoji（😊😂😄），允许功能性符号（✅❌🔴🟡🟢📅💰）。",
            "视频教程链接会自动生成在下方，回复中无需重复输出链接。",
        ])

        return "\n".join(parts)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.openai_base_url,
                timeout=60.0,
                max_retries=2,
            )
        return self._client

    async def _call_tool(
        self, name: str, arguments: dict, user_id: str = "",
        max_retries: int = 3, timeout_seconds: float = 30.0,
        confirmed_dangerous: bool = False,
        confirmed_key: str = "",
    ) -> str:
        """调用工具 — 带重试 + 超时 + 安全护栏"""
        tool = ToolRegistry.get(name)
        if not tool:
            return json.dumps({"error": f"工具不存在: {name}"}, ensure_ascii=False)

        # ═══════════════════════════════════════════════════════
        # 安全护栏：危险操作必须先经用户确认
        # confirmed_key 为 "{tool_name}:{args_hash}"，精确匹配本次调用的工具+参数
        # ═══════════════════════════════════════════════════════
        danger_level = ToolRegistry.get_danger_level(name)
        if danger_level == "dangerous" and not (confirmed_dangerous or confirmed_key):
            return json.dumps({
                "requires_confirmation": True,
                "tool": name,
                "args": arguments,
                "danger_level": danger_level,
                "message": f"即将执行高危操作「{name}」，请确认后再执行。"
            }, ensure_ascii=False)

        # 自动注入 user_id（参数传入，不再依赖实例可变状态）
        if "user_id" not in arguments and user_id:
            arguments["user_id"] = user_id

        # Pydantic 参数校验（如果工具注册时提供了 schema）
        schema = tool.get("parameters", {})
        if schema and schema.get("type") == "object":
            valid_args = {}
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            for key, prop_info in props.items():
                if key in arguments:
                    val = arguments[key]
                    expected_type = prop_info.get("type", "string")
                    try:
                        if expected_type == "integer" and not isinstance(val, int):
                            val = int(val)
                        elif expected_type == "number" and not isinstance(val, (int, float)):
                            val = float(val)
                        elif expected_type == "boolean" and isinstance(val, str):
                            val = val.lower() in ("true", "1", "yes")
                        valid_args[key] = val
                    except (ValueError, TypeError):
                        return json.dumps(
                            {"error": f"参数 {key} 类型错误: 期望 {expected_type}"},
                            ensure_ascii=False,
                        )
                elif key in required:
                    return json.dumps(
                        {"error": f"缺少必需参数: {key}"},
                        ensure_ascii=False,
                    )
                elif key in arguments:
                    valid_args[key] = arguments[key]
            arguments = valid_args

        # ---- 重试循环 ----
        last_error = ""
        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    tool["function"](**arguments),
                    timeout=timeout_seconds,
                )
                if hasattr(result, "model_dump"):
                    return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
                # 处理 list/dict 中包含 Pydantic 模型的情况
                return json.dumps(_serialize_tool_result(result), ensure_ascii=False, default=str)
            except asyncio.TimeoutError:
                last_error = f"工具 {name} 超时({timeout_seconds}s)"
                logger.warning(f"{last_error}，第 {attempt + 1}/{max_retries} 次重试")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                continue
            except Exception as e:
                last_error = str(e)
                logger.warning(f"工具 {name} 失败: {e}，第 {attempt + 1}/{max_retries} 次重试")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                continue

        return json.dumps({"error": last_error}, ensure_ascii=False)

    async def _prepare_context(
        self, request: AgentRequest
    ) -> dict[str, Any]:
        """run/run_stream 共享的准备逻辑：记忆注入、意图路由、Plan-and-Execute、历史加载

        提取这个方法的目的：
        1. 保证两条路径的行为完全一致
        2. 新增功能只改一处
        """
        user_id = request.user_id
        session_id = request.session_id

        # 已确认的工具集合（安全护栏用）— 按 (tool_name, args_json_hash) 粒度确认
        confirmed_set: set[str] = set()
        for item in request.confirmed_tools:
            tool_name = item.get("tool", "")
            args = item.get("args", {})
            args_hash = hashlib.md5(json.dumps(args, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
            confirmed_set.add(f"{tool_name}:{args_hash}")

        # 意图路由
        routed_label = "fallback"
        try:
            from .intent_router import get_intent_router
            intent_label, candidate_tools = await get_intent_router().route(request.message)
            routed_label = intent_label
            routed_tools = [t for t in candidate_tools if t in self.tool_names]
            if len(routed_tools) < 5:
                routed_tools = self.tool_names
        except Exception:
            routed_tools = self.tool_names
        tools = ToolRegistry.list_tools(routed_tools)

        # 记忆注入
        memory_context = ""
        if user_id not in self._memory_injected:
            self._memory_injected.add(user_id)
            try:
                from ..memory.conversation_memory import get_conversation_memory
                mem = get_conversation_memory()
                memory_context = await mem.retrieve_user_summary(user_id)
            except Exception:
                pass

        # 用户档案 + 构建 system prompt
        profile = request.context.get("profile")
        full_prompt = self._build_full_prompt(user_id, profile, memory_context)

        # Plan-and-Execute
        plan_steps = await self._generate_plan(request.message, memory_context)
        if plan_steps:
            plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan_steps))
            full_prompt += (
                f"\n\n## 执行计划\n"
                f"用户的任务已分解为以下步骤，请按顺序逐步执行：\n"
                f"{plan_text}\n\n"
                f"每完成一步后再开始下一步，不要跳过。"
            )

        messages: list[dict[str, Any]] = [{"role": "system", "content": full_prompt}]

        # 历史加载（滑动窗口）
        MAX_FULL = 5
        try:
            from ..memory.conversation_memory import get_conversation_memory
            mem = get_conversation_memory()
            history = await mem.get_history(session_id)
            if len(history) > MAX_FULL:
                old_text = "\n".join(
                    f"{'用户' if h.role == 'user' else '助手'}: {h.content[:200]}"
                    for h in history[:-MAX_FULL][-20:]
                )
                summary = await self._summarize_history(old_text)
                if summary:
                    messages.append({"role": "system", "content": f"[历史对话摘要] {summary}"})
            for h in history[-MAX_FULL:]:
                messages.append({"role": h.role, "content": h.content})
        except Exception:
            pass
        messages.append({"role": "user", "content": request.message})

        logger.debug(
            f"Context prepared: intent={routed_label} "
            f"tools={len(tools)}/{len(self.tool_names)} "
            f"messages={len(messages)} plan={'yes' if plan_steps else 'no'}"
        )

        return {
            "user_id": user_id,
            "session_id": session_id,
            "messages": messages,
            "tools": tools,
            "confirmed_set": confirmed_set,
            "plan_steps_count": len(plan_steps) if plan_steps else 0,
        }

    async def run(self, request: AgentRequest) -> AgentResponse:
        """执行 ReAct 循环 — 全链路追踪 + Token 统计 + 安全确认"""
        t_start = time.time()
        ctx = await self._prepare_context(request)
        user_id = ctx["user_id"]
        session_id = ctx["session_id"]
        messages = ctx["messages"]
        tools = ctx["tools"]
        confirmed_set = ctx["confirmed_set"]

        trace_steps: list[dict] = []
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}
        tool_calls_log = []
        final_text = ""
        partial_texts = []
        video_data_list: list[dict] = []

        # ====== 动态轮次 + 死循环检测 ======
        plan_count = ctx.get("plan_steps_count", 0)
        if plan_count > 1:
            effective_max = min(plan_count * 3 + 2, self.max_iterations)
        else:
            effective_max = 5

        last_tool_sig = ""
        repeat_count = 0
        MAX_REPEAT = 2
        TOKEN_BUDGET = settings.agent_token_budget
        # ===================================

        for iteration in range(effective_max):
            # ---- 防线1: Token 预算 ----
            if total_tokens["total"] > TOKEN_BUDGET:
                final_text = "当前任务较复杂，已为您完成部分处理。如有需要请继续提问。"
                trace_steps.append({
                    "iteration": iteration, "step_type": "token_limit",
                    "detail": {"tokens": total_tokens["total"], "budget": TOKEN_BUDGET},
                    "duration_ms": 0,
                })
                break

            iter_start = time.time()
            # LLM 调用 — 3 次退避重试（应对 API 波动）
            resp = None
            last_llm_error = ""
            for retry in range(3):
                try:
                    resp = await self.client.chat.completions.create(
                        model=settings.openai_model,
                        messages=messages,
                        tools=tools if tools else None,
                        temperature=settings.llm_temperature,
                        parallel_tool_calls=settings.agent_parallel_tools,
                    )
                    break
                except Exception as e:
                    last_llm_error = str(e)
                    if retry < 2:
                        wait = 0.5 * (retry + 1)
                        logger.warning(f"LLM call retry {retry+1}/3 after {wait}s: {e}")
                        await asyncio.sleep(wait)
            if resp is None:
                logger.error(f"LLM call failed after 3 retries: {last_llm_error}")
                final_text = "抱歉，AI 服务暂时不可用，请稍后重试。"
                trace_steps.append({
                    "iteration": iteration, "step_type": "error",
                    "detail": {"error": last_llm_error},
                    "duration_ms": int((time.time() - iter_start) * 1000),
                })
                break

            choice = resp.choices[0]
            msg = choice.message
            iter_duration = int((time.time() - iter_start) * 1000)

            # Token 统计
            usage = resp.usage
            if usage:
                total_tokens["prompt"] += usage.prompt_tokens or 0
                total_tokens["completion"] += usage.completion_tokens or 0
                total_tokens["total"] += usage.total_tokens or 0

            # 工具调用
            if msg.tool_calls:
                # ---- 防线2: 死循环检测 ----
                this_calls = sorted(
                    f"{tc.function.name}:{tc.function.arguments[:120]}"
                    for tc in msg.tool_calls
                )
                this_sig = "|".join(this_calls)
                if this_sig == last_tool_sig and this_sig != "":
                    repeat_count += 1
                    if repeat_count >= MAX_REPEAT:
                        final_text = "抱歉，我在处理时遇到了一些困难。请您换个方式描述需求，我会重新帮您处理。"
                        trace_steps.append({
                            "iteration": iteration, "step_type": "repeat_limit",
                            "detail": {"repeated_calls": this_sig, "count": repeat_count},
                            "duration_ms": 0,
                        })
                        break
                else:
                    repeat_count = 0
                last_tool_sig = this_sig

                if msg.content:
                    partial_texts.append(msg.content)

                # 追踪 LLM 调用
                trace_steps.append({
                    "iteration": iteration, "step_type": "llm_call",
                    "detail": {
                        "thought": msg.content or "",
                        "tool_calls_planned": [
                            {"name": tc.function.name, "args": tc.function.arguments[:200]}
                            for tc in msg.tool_calls
                        ],
                        "tokens": {
                            "prompt": usage.prompt_tokens if usage else 0,
                            "completion": usage.completion_tokens if usage else 0,
                        } if usage else {},
                    },
                    "duration_ms": iter_duration,
                })

                # 并行执行所有工具调用
                tool_tasks = []
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    tool_tasks.append((tc, tool_name, args))

                results = await asyncio.gather(
                    *[self._call_tool(name, args, user_id,
                                      confirmed_key=_make_confirmed_key(name, args, confirmed_set))
                      for _, name, args in tool_tasks],
                    return_exceptions=True,
                )

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc, _, _ in tool_tasks
                    ]
                }
                # DeepSeek thinking 模式：必须回传 reasoning_content
                if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                    assistant_msg["reasoning_content"] = msg.reasoning_content
                messages.append(assistant_msg)

                for (tc, tool_name, args), result in zip(tool_tasks, results):
                    if isinstance(result, Exception):
                        result_str = json.dumps({"error": str(result)}, ensure_ascii=False)
                    else:
                        result_str = result

                    # 共享处理: 安全护栏 → 视频提取 → 自动修复 → 日志追踪
                    result_str, confirm = await self._process_single_tool_result(
                        tool_name, args, result_str, user_id,
                        video_data_list, tool_calls_log, trace_steps, iteration,
                    )
                    if confirm:
                        total_duration = int((time.time() - t_start) * 1000)
                        return AgentResponse(
                            session_id=session_id,
                            response=confirm.get("message", f"即将执行高危操作，请确认：{tool_name}"),
                            intent=request.intent or "general",
                            tool_calls=tool_calls_log,
                            confidence=0.95,
                            requires_confirmation=True,
                            pending_dangerous_calls=[confirm],
                        )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
                continue

            # 纯文本回复
            if msg.content:
                final_text = msg.content
                trace_steps.append({
                    "iteration": iteration, "step_type": "final",
                    "detail": {
                        "response": final_text[:500],
                        "tokens": {
                            "prompt": usage.prompt_tokens if usage else 0,
                            "completion": usage.completion_tokens if usage else 0,
                        } if usage else {},
                    },
                    "duration_ms": iter_duration,
                })
                break

            final_text = "抱歉，我没有理解您的需求。"
            break

        if not final_text:
            final_text = (
                " ".join(partial_texts) + "\n\n以上是根据您的需求处理的结果。"
                if partial_texts
                else "已为您处理完毕，请在结果中查看详情。"
            )
            trace_steps.append({
                "iteration": -1, "step_type": "final",
                "detail": {"response": final_text[:500]},
                "duration_ms": 0,
            })

        # ═══════════════════════════════════════════════════════
        # 自动偏好学习：后台异步提取用户偏好变化（不阻塞响应）
        # ═══════════════════════════════════════════════════════
        self._schedule_preference_extraction(user_id, request.message, final_text)

        # ---- 注入视频卡片（数据已在工具调用时提取） ----
        if video_data_list:
            final_text += self._build_video_cards_html(video_data_list)

        # 动态置信度
        if tool_calls_log:
            success_rate = sum(
                1 for tc in tool_calls_log
                if "error" not in str(tc.get("result", "")).lower()
            ) / max(len(tool_calls_log), 1)
            confidence = round(0.7 + success_rate * 0.25, 2)
        else:
            confidence = 0.9

        # 总耗时
        total_duration = int((time.time() - t_start) * 1000)

        # ---- 持久化追踪记录 + Token 用量 ----
        await self._persist_trace(
            request, final_text, request.intent or "general",
            trace_steps, total_tokens, total_duration, confidence,
        )

        return AgentResponse(
            session_id=request.session_id,
            response=final_text,
            intent="general",
            tool_calls=tool_calls_log,
            data={"videos": video_data_list} if video_data_list else {},
            confidence=confidence,
        )

    async def _persist_trace(
        self, request: AgentRequest, response: str, intent: str,
        steps: list[dict], tokens: dict, total_duration_ms: int, confidence: float,
    ):
        """后台持久化追踪记录 + Token 用量"""
        try:
            from ..models.database import get_db, TraceRecord, TokenUsageRecord

            async for session in get_db():
                for step in steps:
                    trace_id = f"trc_{uuid.uuid4().hex[:12]}"
                    session.add(TraceRecord(
                        trace_id=trace_id,
                        session_id=request.session_id,
                        user_id=request.user_id,
                        agent_name=self.name,
                        intent=intent,
                        user_message=request.message[:500],
                        iteration=step.get("iteration", 0),
                        step_type=step.get("step_type", "unknown"),
                        detail={
                            **step.get("detail", {}),
                            "agent": self.name,
                        },
                        duration_ms=step.get("duration_ms", 0),
                    ))

                # Token 用量记录
                if tokens["total"] > 0:
                    price = TOKEN_PRICES.get(settings.openai_model, TOKEN_PRICES["default"])
                    cost = (
                        tokens["prompt"] / 1_000_000 * price["prompt"]
                        + tokens["completion"] / 1_000_000 * price["completion"]
                    )
                    session.add(TokenUsageRecord(
                        record_id=f"tku_{uuid.uuid4().hex[:12]}",
                        user_id=request.user_id,
                        session_id=request.session_id,
                        model=settings.openai_model,
                        prompt_tokens=tokens["prompt"],
                        completion_tokens=tokens["completion"],
                        total_tokens=tokens["total"],
                        estimated_cost_cny=round(cost, 6),
                        endpoint="/api/v1/agent/chat",
                    ))

                await session.commit()
                logger.debug(f"Trace persisted: {len(steps)} steps, {tokens['total']} tokens, {total_duration_ms}ms")
        except Exception as e:
            logger.debug(f"Trace persist skipped: {e}")

    async def run_stream(self, request: AgentRequest) -> AsyncGenerator[str, None]:
        """流式执行 ReAct 循环（含滑动窗口摘要，历史 <= 3000 tokens）

        关键：LLM 在调工具前的"思考文本"不会被 yield——只有最终回复才会推送给前端。
        视频卡片 HTML 通过 contextvars 按请求隔离，由路由层以独立 SSE 事件发送。

        与 run() 共享 _prepare_context()，保证准备阶段行为一致。
        """
        ctx = await self._prepare_context(request)
        user_id = ctx["user_id"]
        session_id = ctx["session_id"]
        messages = ctx["messages"]
        tools = ctx["tools"]
        stream_confirmed_set = ctx["confirmed_set"]

        full_text = ""
        video_results: list[dict] = []
        _video_html_var.set("")
        pending_confirmations: list[dict] = []

        # ═══════════════════════════════════════════════════════
        # 追踪变量
        # ═══════════════════════════════════════════════════════
        t_start = time.time()
        trace_steps: list[dict] = []
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}
        tool_calls_log: list[dict] = []

        # ====== 动态轮次 + 死循环检测（流式版本） ======
        plan_count = ctx.get("plan_steps_count", 0)
        if plan_count > 1:
            effective_max = min(plan_count * 3 + 2, self.max_iterations)
        else:
            effective_max = 5

        last_tool_sig = ""
        repeat_count = 0
        MAX_REPEAT = 2
        TOKEN_BUDGET = settings.agent_token_budget
        # ==============================================

        for iteration in range(effective_max):
            # ---- 防线1: Token 预算 ----
            if total_tokens["total"] > TOKEN_BUDGET:
                full_text = "当前任务较复杂，已为您完成部分处理。如有需要请继续提问。"
                yield full_text
                trace_steps.append({
                    "iteration": iteration, "step_type": "token_limit",
                    "detail": {"tokens": total_tokens["total"], "budget": TOKEN_BUDGET},
                    "duration_ms": 0,
                })
                break

            iter_start = time.time()
            # LLM 流式调用 — 3 次退避重试
            resp = None
            last_llm_error = ""
            for retry_count in range(3):
                try:
                    resp = await self.client.chat.completions.create(
                        model=settings.openai_model,
                        messages=messages,
                        tools=tools if tools else None,
                        temperature=settings.llm_temperature,
                        stream=True,
                        stream_options={"include_usage": True},
                    )
                    break
                except Exception as e:
                    last_llm_error = str(e)
                    if retry_count < 2:
                        wait = 0.5 * (retry_count + 1)
                        logger.warning(f"LLM stream retry {retry_count+1}/3 after {wait}s: {e}")
                        await asyncio.sleep(wait)
            if resp is None:
                logger.error(f"LLM stream failed after 3 retries: {last_llm_error}")
                full_text = "抱歉，AI 服务暂时不可用，请稍后重试。"
                yield full_text
                trace_steps.append({
                    "iteration": iteration, "step_type": "error",
                    "detail": {"error": last_llm_error},
                    "duration_ms": int((time.time() - iter_start) * 1000),
                })
                break

            content_chunks: list[str] = []  # 缓冲内容——不立即 yield（可能是调工具前的"思考"）
            reasoning_chunks: list[str] = []  # 收集 reasoning_content
            tool_call_chunks: dict[int, dict] = {}
            stream_usage = None  # 流式最后的 usage chunk
            async for chunk in resp:
                # 捕获流式 Token 用量（最后一个 chunk 无 choices 但有 usage）
                if chunk.usage:
                    stream_usage = chunk.usage
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                # 捕获 reasoning_content（DeepSeek thinking 模式），必须回传否则 API 报 400
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_chunks.append(delta.reasoning_content)
                if delta.content:
                    content_chunks.append(delta.content)
                    # 不 yield——等确认这不是"思考"而是最终回复后再推送
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                        if tc.function:
                            if tc.function.name:
                                tool_call_chunks[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_chunks[idx]["arguments"] += tc.function.arguments
                        if tc.id:
                            tool_call_chunks[idx]["id"] = tc.id

            content_text = "".join(content_chunks)
            reasoning_text = "".join(reasoning_chunks)
            iter_duration = int((time.time() - iter_start) * 1000)

            # 累计 Token 用量
            if stream_usage:
                total_tokens["prompt"] += stream_usage.prompt_tokens or 0
                total_tokens["completion"] += stream_usage.completion_tokens or 0
                total_tokens["total"] += stream_usage.total_tokens or 0
            iter_tokens = {
                "prompt": stream_usage.prompt_tokens if stream_usage else 0,
                "completion": stream_usage.completion_tokens if stream_usage else 0,
            }

            # 纯文本回复（无工具调用）→ 这是最终答案，推送给前端
            if content_text and not tool_call_chunks:
                trace_steps.append({
                    "iteration": iteration, "step_type": "final",
                    "detail": {"response": content_text[:500], "tokens": iter_tokens},
                    "duration_ms": iter_duration,
                })
                yield content_text
                full_text = content_text
                break

            # 有工具调用 → 并行执行（与 run() 一致）
            if tool_call_chunks:
                # ---- 防线2: 死循环检测（流式版本） ----
                this_calls = sorted(
                    f"{tc['name']}:{tc['arguments'][:120]}"
                    for tc in tool_call_chunks.values()
                )
                this_sig = "|".join(this_calls)
                if this_sig == last_tool_sig and this_sig != "":
                    repeat_count += 1
                    if repeat_count >= MAX_REPEAT:
                        full_text = "抱歉，我在处理时遇到了一些困难。请您换个方式描述需求。"
                        yield full_text
                        trace_steps.append({
                            "iteration": iteration, "step_type": "repeat_limit",
                            "detail": {"repeated_calls": this_sig, "count": repeat_count},
                            "duration_ms": 0,
                        })
                        break
                else:
                    repeat_count = 0
                last_tool_sig = this_sig

                # 追踪 LLM 调用（调工具前）
                trace_steps.append({
                    "iteration": iteration, "step_type": "llm_call",
                    "detail": {
                        "thought": content_text or "",
                        "tool_calls_planned": [
                            {"name": tc["name"], "args": tc["arguments"][:200]}
                            for tc in tool_call_chunks.values()
                        ],
                        "tokens": iter_tokens,
                    },
                    "duration_ms": iter_duration,
                })

                # 收集所有工具调用任务
                tool_tasks: list[tuple[int, str, dict, str]] = []
                for idx, tc_data in tool_call_chunks.items():
                    tool_name = tc_data["name"]
                    try:
                        args = json.loads(tc_data["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    call_id = tc_data["id"] or f"call_{idx}"
                    tool_tasks.append((idx, tool_name, args, call_id))

                # 并行执行所有工具
                results = await asyncio.gather(
                    *[self._call_tool(name, args, user_id,
                                      confirmed_key=_make_confirmed_key(name, args, stream_confirmed_set))
                      for _, name, args, _ in tool_tasks],
                    return_exceptions=True,
                )

                # 处理结果 + 构建消息
                for (idx, tool_name, args, call_id), tool_result in zip(tool_tasks, results):
                    if isinstance(tool_result, Exception):
                        tool_result = json.dumps({"error": str(tool_result)}, ensure_ascii=False)

                    # 共享处理: 安全护栏 → 视频提取 → 自动修复 → 日志追踪
                    tool_result, confirm = await self._process_single_tool_result(
                        tool_name, args, tool_result, user_id,
                        video_results, tool_calls_log, trace_steps, iteration,
                    )
                    if confirm:
                        pending_confirmations.append(confirm)
                        continue  # 不加入消息历史，等待用户确认后重发

                    assistant_msg: dict = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": call_id,
                            "type": "function",
                            "function": {"name": tool_name, "arguments": tool_call_chunks[idx]["arguments"]}
                        }]
                    }
                    # DeepSeek thinking 模式：必须回传 reasoning_content，否则 400
                    if reasoning_text:
                        assistant_msg["reasoning_content"] = reasoning_text
                    messages.append(assistant_msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": tool_result,
                    })
                continue

            if content_text:
                trace_steps.append({
                    "iteration": iteration, "step_type": "final",
                    "detail": {"response": content_text[:500], "tokens": iter_tokens},
                    "duration_ms": iter_duration,
                })
                full_text = content_text
                break
            break

        # ═══════════════════════════════════════════════════════
        # 如果有待确认的高危操作，停止正常流程，返回确认请求
        # ═══════════════════════════════════════════════════════
        if pending_confirmations:
            confirm_msg = pending_confirmations[0].get("message", "有操作需要您的确认")
            yield json.dumps({
                "requires_confirmation": True,
                "content": confirm_msg,
                "pending_dangerous_calls": pending_confirmations,
            }, ensure_ascii=False)
            return  # 不继续执行，等待用户确认后重发

        if not full_text:
            full_text = "处理完成。"
            yield full_text
            trace_steps.append({
                "iteration": -1, "step_type": "final",
                "detail": {"response": full_text[:500]},
                "duration_ms": 0,
            })

        # ---- 持久化追踪记录 + Token 用量（补齐流式路径） ----
        total_duration = int((time.time() - t_start) * 1000)
        if tool_calls_log:
            success_rate = sum(
                1 for tc in tool_calls_log
                if "error" not in str(tc.get("result", "")).lower()
            ) / max(len(tool_calls_log), 1)
            confidence = round(0.7 + success_rate * 0.25, 2)
        else:
            confidence = 0.9
        await self._persist_trace(
            request, full_text, request.intent or "general",
            trace_steps, total_tokens, total_duration, confidence,
        )

        # 构建视频卡片 HTML（contextvars 隔离，并发安全）
        if video_results:
            _video_html_var.set(self._build_video_cards_html(video_results))

        # 持久化对话历史到 ConversationMemory（流式路由不做持久化，在此补上）
        try:
            from ..memory.conversation_memory import get_conversation_memory
            from ..models.schemas import ConversationMessage
            mem = get_conversation_memory()
            await mem.add_message(session_id, ConversationMessage(role="user", content=request.message), user_id=user_id)
            await mem.add_message(session_id, ConversationMessage(role="assistant", content=full_text), user_id=user_id)
        except Exception as e:
            logger.debug(f"Stream memory persist skipped: {e}")

        # ═══════════════════════════════════════════════════════
        # 自动偏好学习（流式版本）：后台异步提取，不阻塞
        # ═══════════════════════════════════════════════════════
        self._schedule_preference_extraction(user_id, request.message, full_text)

    async def _generate_plan(self, user_message: str, context: str = "") -> list[str] | None:
        """检测复杂任务并生成执行计划

        对包含多个意图的消息（如"检查冰箱库存，规划菜谱，生成购物清单"），
        LLM 将其分解为有序的子任务列表。简单消息返回 None。
        """
        # 快速判断：消息太短或明显单一意图 → 跳过
        msg = user_message.strip()
        if len(msg) < 15:
            return None

        # 多意图关键词检测
        multi_intent_kw = ["然后", "接着", "再", "同时", "顺便", "还有", "以及",
                           "之后", "最后", "先", "并", "并且"]
        if not any(kw in msg for kw in multi_intent_kw):
            return None

        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是任务分解助手。将用户的复杂请求拆成有序的执行步骤。\n"
                        "每行一个步骤，用中文。不要编号，不要解释，最多5步。\n"
                        "如果请求很简单（单一步骤），直接输出 NONE。"
                    ),
                }, {
                    "role": "user",
                    "content": f"用户请求：{msg[:500]}",
                }],
                temperature=0,
                max_tokens=200,
            )
            plan_text = (resp.choices[0].message.content or "").strip()
            if not plan_text or plan_text.upper() == "NONE":
                return None

            steps = [s.strip() for s in plan_text.split("\n") if s.strip()]
            if len(steps) <= 1:
                return None

            logger.info(f"Plan generated: {len(steps)} steps → {steps[:3]}...")
            return steps[:5]
        except Exception as e:
            logger.debug(f"Plan generation skipped: {e}")
            return None

    async def _summarize_history(self, dialog_text: str) -> str:
        """LLM 压缩对话历史（保持 <= 3000 tokens 上限）"""
        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": "用一句话（不超过 100 字）总结以下对话的核心内容和达成的决策。只输出总结本身。",
                }, {
                    "role": "user",
                    "content": dialog_text[:2000],
                }],
                temperature=0.1,
                max_tokens=120,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return ""

    async def _auto_fix_and_retry(
        self, tool_name: str, args: dict, error_msg: str, user_id: str,
    ) -> tuple[dict | None, str]:
        """自动分析并修复工具参数错误，重试一次

        常见可修复错误：
        1. appliance_id 不存在 → 尝试从错误信息中提取正确 ID
        2. 参数类型错误 → 尝试类型转换
        3. 缺少必需参数 → 尝试从错误信息推断

        Returns:
            (fixed_args, result_str) 或 (None, original_error)
        """
        # 用 LLM 分析错误并生成修复后的参数
        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是参数修复助手。工具调用失败，分析错误原因并输出修复后的 JSON 参数。"
                        "只输出 JSON，不要解释。如果无法修复输出 {\"unfixable\": true}。"
                    ),
                }, {
                    "role": "user",
                    "content": (
                        f"工具名: {tool_name}\n"
                        f"原参数: {json.dumps(args, ensure_ascii=False)}\n"
                        f"错误信息: {error_msg[:500]}\n\n"
                        f"请输出修复后的 JSON 参数:"
                    ),
                }],
                temperature=0,
                max_tokens=300,
            )
            content = resp.choices[0].message.content or "{}"
            # 清理可能的 markdown 包裹
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            fixed = json.loads(content.strip())

            if fixed.get("unfixable"):
                return None, error_msg

            if fixed == args:
                return None, error_msg  # 没有实质性修改

            # 重试修复后的参数
            logger.info(f"Auto-fix: {tool_name} args {args} → {fixed}")
            result_str = await self._call_tool(
                tool_name, fixed, user_id, max_retries=1, timeout_seconds=15.0,
            )
            return fixed, result_str
        except Exception as e:
            logger.debug(f"Auto-fix failed: {e}")
            return None, error_msg

    async def _process_single_tool_result(
        self, tool_name: str, args: dict, result_str: str, user_id: str,
        video_data_list: list[dict], tool_calls_log: list[dict],
        trace_steps: list[dict], iteration: int,
    ) -> tuple[str, dict | None]:
        """处理单个工具调用结果: 安全护栏 → 视频提取 → 自动修复 → 日志追踪

        run() 和 run_stream() 共享此方法，确保工具结果处理逻辑一致。

        Returns:
            (result_str, confirmation_dict_or_None)
        """
        # 安全护栏检测
        if "requires_confirmation" in result_str:
            try:
                confirm_data = json.loads(result_str)
                if confirm_data.get("requires_confirmation"):
                    logger.info(
                        f"Safety guard: tool '{tool_name}' requires user confirmation"
                    )
                    return result_str, {
                        "tool": tool_name,
                        "args": args,
                        "message": confirm_data.get("message", f"确认执行 {tool_name}？"),
                    }
            except json.JSONDecodeError:
                pass

        # 视频工具：当场提取视频数据
        if tool_name == "search_recipe_videos" and "error" not in result_str.lower():
            try:
                vr = json.loads(result_str)
                if vr.get("videos"):
                    video_data_list.extend(vr["videos"])
            except Exception:
                pass

        # 自动修复：工具返回错误时尝试修参重试
        auto_fixed = False
        if "error" in result_str.lower():
            tool_danger = ToolRegistry.get_danger_level(tool_name)
            if tool_danger != "dangerous":
                fixed_args, retry_result = await self._auto_fix_and_retry(
                    tool_name, args, result_str, user_id,
                )
                if fixed_args is not None:
                    result_str = retry_result
                    args = fixed_args
                    auto_fixed = True

        # 追踪日志
        result_summary = result_str[:300]
        if auto_fixed:
            result_summary = "[auto-fixed] " + result_summary
        tool_calls_log.append({
            "tool": tool_name,
            "args": args,
            "result": result_summary,
        })
        trace_steps.append({
            "iteration": iteration, "step_type": "tool_result",
            "detail": {
                "tool": tool_name,
                "args": {k: str(v)[:100] for k, v in args.items()},
                "result_summary": result_summary,
                "is_error": "error" in result_summary.lower(),
            },
            "duration_ms": 0,
        })

        return result_str, None

    @staticmethod
    def _build_video_cards_html(video_list: list[dict]) -> str:
        """构建视频卡片 HTML（run/run_stream 共享）"""
        if not video_list:
            return ""
        import hashlib
        from urllib.parse import quote
        cards = ""
        for v in video_list[:3]:
            thumb = v.get("thumbnail", "")
            title = v.get("title", "")
            url = v.get("url", "")
            author = v.get("author", "")
            duration = v.get("duration", "")
            plays = v.get("play_count", "")
            hue = int(hashlib.md5(title.encode()).hexdigest()[:4], 16) % 360
            # 封面图：优先使用 B 站缩略图（通过代理绕过防盗链），渐变色兜底
            bg_style = (
                f'background:url(/api/v1/agent/proxy-image?url={quote(thumb, safe="")}) center/cover no-repeat,'
                f'linear-gradient(135deg,hsl({hue},70%,45%),hsl({(hue+40)%360},70%,30%))'
            ) if thumb else (
                f'background:linear-gradient(135deg,hsl({hue},70%,45%),hsl({(hue+40)%360},70%,30%))'
            )
            cards += (
                f'<a class="video-card" href="{url}" target="_blank" rel="noopener">'
                f'<div class="video-thumb" style="{bg_style}">'
                f'<span class="video-duration">{duration}</span>'
                f'</div>'
                f'<div class="video-meta">'
                f'<span class="video-title">{title[:40]}</span>'
                f'<span class="video-info">B站 · {author} · {plays}播放</span>'
                f'</div>'
                f'</a>'
            )
        return f'<!--VIDEOS--><div class="video-cards">{cards}</div><!--/VIDEOS-->'

    def _schedule_preference_extraction(
        self, user_id: str, user_message: str, agent_response: str,
    ):
        """后台调度偏好提取（防抖：同一用户 10 分钟内不重复提取）"""
        now = time.time()
        last = self._last_preference_extraction.get(user_id, 0)
        if now - last < 600:  # 10 分钟防抖
            return
        self._last_preference_extraction[user_id] = now

        dialog = f"用户: {user_message[:500]}\n助手: {agent_response[:500]}"
        asyncio.create_task(self._extract_preferences_bg(user_id, dialog))

    async def _extract_preferences_bg(self, user_id: str, dialog_text: str):
        """后台：从对话中提取偏好变化并自动写入用户画像"""
        try:
            from ..memory.conversation_memory import get_conversation_memory
            mem = get_conversation_memory()
            result = await mem.extract_and_update_preferences(user_id, dialog_text)
            if result:
                logger.info(f"Preference auto-updated for {user_id}: {result.get('summary', '')}")
        except Exception as e:
            logger.debug(f"Preference extraction background task failed: {e}")


# ========== 工具注册 ==========
def register_all_tools():
    from ..tools.shopping_tools import (
        get_fridge_inventory, add_to_shopping_list,
        compare_supermarket_prices, generate_shopping_list, search_product_prices,
        add_fridge_item, remove_fridge_item, record_shopping,
    )
    from ..tools.recipe_tools import (
        search_recipes, get_recipe_detail,
        generate_meal_plan, match_recipes_by_ingredients
    )
    from ..tools.appliance_tools import (
        get_appliance_status, schedule_appliance,
        generate_off_peak_schedule, control_smart_appliance
    )
    from ..tools.maintenance_tools import (
        check_maintenance_due, create_maintenance_task,
        find_service_contact, send_maintenance_reminder
    )
    from ..tools.notification_tools import send_notification, send_bill_reminder
    from ..tools.calendar_tools import (
        get_weekly_schedule, add_calendar_event,
        find_free_time_slots, schedule_task
    )
    from ..tools.web_search_tools import web_search, search_recipe_videos
    from ..tools.security_tools import (
        check_door_status, check_window_status,
        check_camera_feeds, get_security_events,
        set_away_mode, get_elderly_activity,
    )
    from ..tools.household_tools import (
        track_packages, get_community_notices, add_tracking,
    )

    # Security tools
    ToolRegistry.register("check_door_status", check_door_status,
        "检查全部门锁状态（入户门/阳台门/车库门）",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("check_window_status", check_window_status,
        "检查所有窗户开关状态",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("check_camera_feeds", check_camera_feeds,
        "检查所有安防摄像头画面和今日事件",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("get_security_events", get_security_events,
        "获取最近的安防事件日志",
        {"type":"object","properties":{"user_id":{"type":"string"},"limit":{"type":"integer"}},"required":["user_id"]})
    ToolRegistry.register("set_away_mode", set_away_mode,
        "设置离家布防模式：关门窗、设防、关灯、家电节能",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]},
        danger_level="dangerous")
    ToolRegistry.register("get_elderly_activity", get_elderly_activity,
        "查看老人活动状态和今日活动规律",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})

    # Household tools
    ToolRegistry.register("track_packages", track_packages,
        "追踪在途快递包裹状态",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("add_tracking", add_tracking,
        "录入快递单号以便追踪。参数：tracking_id(快递单号)、carrier(快递公司，如顺丰/圆通/中通)、description(可选备注)",
        {"type":"object","properties":{"user_id":{"type":"string"},"tracking_id":{"type":"string"},"carrier":{"type":"string"},"description":{"type":"string"}},"required":["user_id","tracking_id"]})
    ToolRegistry.register("get_community_notices", get_community_notices,
        "获取社区通知和近期活动",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})

    ToolRegistry.register("get_fridge_inventory", get_fridge_inventory,
        "查看冰箱里有哪些食材，包括数量、过期日期、存放位置",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("add_to_shopping_list", add_to_shopping_list,
        "把商品加入购物清单",
        {"type":"object","properties":{"list_id":{"type":"string"},"item_name":{"type":"string"},"quantity":{"type":"number"},"unit":{"type":"string"},"category":{"type":"string"},"notes":{"type":"string"}},"required":["list_id","item_name"]})
    ToolRegistry.register("compare_supermarket_prices", compare_supermarket_prices,
        "对比盒马、永辉、美团、叮咚等超市的某个商品价格，返回从低到高排序",
        {"type":"object","properties":{"item_name":{"type":"string"},"supermarkets":{"type":"array","items":{"type":"string"}}},"required":["item_name"]})
    ToolRegistry.register("generate_shopping_list", generate_shopping_list,
        "根据冰箱库存和菜谱计划，智能生成购物清单，自动比价推荐最优超市",
        {"type":"object","properties":{"user_id":{"type":"string"},"meal_plan":{"type":"object"},"preferences":{"type":"array","items":{"type":"string"}}},"required":["user_id"]})
    ToolRegistry.register("search_product_prices", search_product_prices,
        "模糊搜索商品，返回各超市价格",
        {"type":"object","properties":{"query":{"type":"string"},"city":{"type":"string"}},"required":["query"]})
    ToolRegistry.register("add_fridge_item", add_fridge_item,
        "往冰箱里添加食材。用户说买了东西时调用。同名食材自动累加数量",
        {"type":"object","properties":{"user_id":{"type":"string"},"name":{"type":"string"},"quantity":{"type":"number"},"unit":{"type":"string"},"category":{"type":"string"},"expiry_days":{"type":"integer"}},"required":["user_id","name"]})
    ToolRegistry.register("remove_fridge_item", remove_fridge_item,
        "从冰箱移除食材（吃掉了/用完了）",
        {"type":"object","properties":{"user_id":{"type":"string"},"name":{"type":"string"},"quantity":{"type":"number"}},"required":["user_id","name"]})
    ToolRegistry.register("record_shopping", record_shopping,
        "记录一次购物：批量入库食材并保存购物记录",
        {"type":"object","properties":{"user_id":{"type":"string"},"items":{"type":"array"},"supermarket":{"type":"string"}},"required":["user_id","items"]})
    ToolRegistry.register("search_recipes", search_recipes,
        "搜索菜谱，可按菜系/类型/时间/标签筛选",
        {"type":"object","properties":{"query":{"type":"string"},"meal_type":{"type":"string"},"cuisine":{"type":"string"},"max_cooking_time":{"type":"integer"},"tags":{"type":"array","items":{"type":"string"}},"limit":{"type":"integer"}},"required":[]})
    ToolRegistry.register("get_recipe_detail", get_recipe_detail,
        "获取某道菜的详细做法、食材清单、烹饪步骤",
        {"type":"object","properties":{"recipe_id":{"type":"string"}},"required":["recipe_id"]})
    ToolRegistry.register("generate_meal_plan", generate_meal_plan,
        "根据冰箱里的食材，智能规划未来N天的一日三餐菜谱",
        {"type":"object","properties":{"user_id":{"type":"string"},"fridge_inventory":{"type":"array"},"preferences":{"type":"array"},"allergies":{"type":"array"},"start_date":{"type":"string"},"days":{"type":"integer"}},"required":["user_id","fridge_inventory"]})
    ToolRegistry.register("match_recipes_by_ingredients", match_recipes_by_ingredients,
        "根据现有食材，看看能做什么菜，按匹配度排序",
        {"type":"object","properties":{"fridge_ingredients":{"type":"array","items":{"type":"string"}},"meal_type":{"type":"string"},"limit":{"type":"integer"}},"required":["fridge_ingredients"]})
    ToolRegistry.register("get_appliance_status", get_appliance_status,
        "查看所有家电的状态",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("schedule_appliance", schedule_appliance,
        "预约家电在指定时间运行（自动错峰）",
        {"type":"object","properties":{"user_id":{"type":"string"},"appliance_id":{"type":"string"},"start_time":{"type":"string"},"end_time":{"type":"string"},"task":{"type":"string"},"force_off_peak":{"type":"boolean"}},"required":["user_id","appliance_id","start_time"]})
    ToolRegistry.register("generate_off_peak_schedule", generate_off_peak_schedule,
        "一键生成今晚错峰运行计划（洗碗机→洗衣机→扫地机，谷电0.3元/度）",
        {"type":"object","properties":{"user_id":{"type":"string"},"date_str":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("control_smart_appliance", control_smart_appliance,
        "控制智能家电开关/暂停/恢复",
        {"type":"object","properties":{"user_id":{"type":"string"},"appliance_id":{"type":"string"},"action":{"type":"string"}},"required":["user_id","appliance_id","action"]},
        danger_level="dangerous")
    ToolRegistry.register("check_maintenance_due", check_maintenance_due,
        "检查所有家电的维保到期情况，返回离下次保养还有多少天",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("create_maintenance_task", create_maintenance_task,
        "创建一条维保任务",
        {"type":"object","properties":{"user_id":{"type":"string"},"appliance_id":{"type":"string"},"appliance_name":{"type":"string"},"task_type":{"type":"string"},"description":{"type":"string"},"priority":{"type":"string"}},"required":["user_id","appliance_id","appliance_name","task_type","description"]})
    ToolRegistry.register("find_service_contact", find_service_contact,
        "根据家电类型查找附近维修师傅的电话和评分",
        {"type":"object","properties":{"appliance_type":{"type":"string"},"location":{"type":"string"}},"required":["appliance_type"]})
    ToolRegistry.register("send_maintenance_reminder", send_maintenance_reminder,
        "发送维保提醒通知",
        {"type":"object","properties":{"user_id":{"type":"string"},"task_id":{"type":"string"},"contact":{"type":"string"}},"required":["user_id","task_id"]},
        danger_level="caution")
    ToolRegistry.register("send_notification", send_notification,
        "向用户发送通知（App推送/短信/邮件）",
        {"type":"object","properties":{"user_id":{"type":"string"},"title":{"type":"string"},"body":{"type":"string"},"channel":{"type":"string"},"priority":{"type":"string"}},"required":["user_id","title","body"]},
        danger_level="caution")
    ToolRegistry.register("send_bill_reminder", send_bill_reminder,
        "检查水电煤物业宽带账单，自动发送缴费提醒",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]},
        danger_level="caution")
    ToolRegistry.register("get_weekly_schedule", get_weekly_schedule,
        "查看这一周的日程安排",
        {"type":"object","properties":{"user_id":{"type":"string"},"start_date":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("find_free_time_slots", find_free_time_slots,
        "查找某天的空闲时间段",
        {"type":"object","properties":{"user_id":{"type":"string"},"target_date":{"type":"string"},"min_duration_minutes":{"type":"integer"}},"required":["user_id","target_date"]})
    ToolRegistry.register("schedule_task", schedule_task,
        "智能安排一个任务到空闲时段",
        {"type":"object","properties":{"user_id":{"type":"string"},"task_name":{"type":"string"},"target_date":{"type":"string"},"duration_minutes":{"type":"integer"},"preferred_time":{"type":"string"}},"required":["user_id","task_name","target_date","duration_minutes"]})
    ToolRegistry.register("web_search", web_search,
        "搜索互联网获取信息（知识库无结果时的兜底方案）。参数query为搜索关键词，max_results为最大结果数",
        {"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"integer"}},"required":["query"]})
    ToolRegistry.register("search_recipe_videos", search_recipe_videos,
        "在B站搜索烹饪教学视频。当用户询问某道菜怎么做时使用，返回视频链接、封面、时长、播放量、作者。参数query为菜名+做法，如'红烧肉做法'",
        {"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"integer"}},"required":["query"]})

    # 视觉识别工具
    from ..tools.vision_tools import analyze_image
    ToolRegistry.register("analyze_image", analyze_image,
        "分析图片内容。当用户上传图片（如冰箱照片、食材照片、家电照片）时调用。参数image_base64为图片的base64编码，prompt为可选的分析提示。",
        {"type":"object","properties":{"image_base64":{"type":"string"},"prompt":{"type":"string"}},"required":["image_base64"]})

    # 知识库检索工具
    async def search_knowledge_base(query: str = "", top_k: int = 5):
        """搜索家庭知识库（食材信息、家电维保记录、菜谱做法、家庭日程等）"""
        from ..rag.qa_chain import get_rag_chain
        chain = get_rag_chain()
        result = await chain.query(question=query)
        return {
            "answer": result.get("answer", ""),
            "sources_count": result.get("sources_count", 0),
            "sources": [s.get("text", "")[:200] for s in result.get("sources", [])]
        }
    ToolRegistry.register("search_knowledge_base", search_knowledge_base,
        "搜索家庭长期记忆知识库（BGE-M3向量检索+Reranker精排），涵盖食材、菜谱、家电维保记录、家庭日程等。当用户问及历史记录或需要查资料时优先使用",
        {"type":"object","properties":{"query":{"type":"string","description":"搜索关键词或问题"},"top_k":{"type":"integer","description":"返回结果数，默认5"}},"required":["query"]})

    # ═══════════════════════════════════════════════════════════
    # 记忆系统工具 — recall_user_memory
    # ═══════════════════════════════════════════════════════════
    async def recall_user_memory(user_id: str = "", query: str = "", top_k: int = 5):
        """检索用户跨会话的长期记忆（已固化的对话摘要和偏好）

        与 search_knowledge_base 的区别：
        - search_knowledge_base 查的是结构化文档（菜谱知识、维保记录）
        - recall_user_memory 查的是用户历史对话摘要（偏好习惯、说过的事、待办事项）

        当用户提到"上次、之前、我们聊过、你还记得吗、我提到过"等回溯性表述时优先使用。
        新对话开始时也应该调用一次，了解用户的背景和偏好。
        """
        from ..memory.conversation_memory import get_conversation_memory
        mem = get_conversation_memory()
        memories = await mem.retrieve_user_memories(
            user_id=user_id, query=query, top_k=top_k,
        )
        if not memories:
            return {"found": 0, "memories": [],
                    "hint": "该用户暂无长期记忆，这是第一次对话或旧记忆已过期"}
        return {
            "found": len(memories),
            "memories": [
                {"text": m["text"][:200], "timestamp": m.get("timestamp", ""), "score": m.get("score", 0)}
                for m in memories
            ],
        }
    ToolRegistry.register("recall_user_memory", recall_user_memory,
        "检索用户跨会话长期记忆（历史对话摘要、偏好习惯、待办事项）。当用户说'上次/之前/还记得吗/我们聊过'时优先使用。新对话开始时也应调用，了解用户背景。",
        {"type":"object","properties":{"user_id":{"type":"string","description":"用户ID"},"query":{"type":"string","description":"要搜索的关键词或问题，留空则返回最近记忆"},"top_k":{"type":"integer","description":"返回记忆条数，默认5"}},"required":["user_id"]})