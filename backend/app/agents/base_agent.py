"""
Agent 基类 v5.2 — ReAct Agent + Function Calling + 全链路追踪 + 重试 + Token统计
新增: 执行追踪、工具重试(3次)、超时控制(30s)、Token用量记录
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any, Callable, AsyncGenerator

from openai import AsyncOpenAI
from loguru import logger

from ..models.schemas import AgentRequest, AgentResponse, ConversationMessage
from ..config import settings

# Token 价格 (元/百万tokens) — DeepSeek 官方价格
TOKEN_PRICES = {
    "deepseek-chat": {"prompt": 1.0, "completion": 2.0},
    "deepseek-reasoner": {"prompt": 4.0, "completion": 16.0},
    "gpt-4o": {"prompt": 18.0, "completion": 54.0},
    "gpt-4o-mini": {"prompt": 1.0, "completion": 3.0},
    "default": {"prompt": 1.0, "completion": 2.0},
}


class ToolRegistry:
    """工具注册表 — 全局单例"""
    _tools: dict[str, dict] = {}

    @classmethod
    def register(cls, name: str, func: Callable, description: str, parameters: dict):
        cls._tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
        }

    @classmethod
    def get(cls, name: str) -> dict | None:
        return cls._tools.get(name)

    @classmethod
    def get_all(cls) -> dict:
        return cls._tools

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
        self.history: list[ConversationMessage] = []
        self.max_iterations = settings.agent_max_iterations
        self._client: AsyncOpenAI | None = None
        self._current_user_id: str = ""

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
        self, name: str, arguments: dict, max_retries: int = 3, timeout_seconds: float = 30.0
    ) -> str:
        """调用工具 — 带重试 + 超时"""
        tool = ToolRegistry.get(name)
        if not tool:
            return json.dumps({"error": f"工具不存在: {name}"}, ensure_ascii=False)

        # 自动注入 user_id
        if "user_id" not in arguments and self._current_user_id:
            arguments["user_id"] = self._current_user_id

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

    async def run(self, request: AgentRequest) -> AgentResponse:
        """执行 ReAct 循环 — 全链路追踪 + Token 统计"""
        t_start = time.time()
        self._current_user_id = request.user_id
        self.history.append(ConversationMessage(role="user", content=request.message))

        # 追踪记录列表
        trace_steps: list[dict] = []
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}

        tools = ToolRegistry.list_tools(self.tool_names)
        full_prompt = (
            f"{self.system_prompt}\n\n"
            f"当前用户ID: {request.user_id}。当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}。\n"
            f"规则：优先调用工具获取实时数据再回答，同一工具可多次调用（参数不同时）。\n"
            f"回复格式：口语化中文。禁止面部表情 emoji（😊😂😄等），允许功能性符号（✅❌🔴🟡🟢📅💰）。禁止 Markdown 符号（# | ** `）。\n"
            f"不要生成任何网页链接 URL。如需引导用户去某个平台，只说平台名称即可（如：打开盒马App搜索）。"
        )
        messages = [{"role": "system", "content": full_prompt}]
        for h in self.history[-settings.conversation_history_limit:]:
            messages.append({"role": h.role, "content": h.content})

        tool_calls_log = []
        final_text = ""
        partial_texts = []
        video_data_list: list[dict] = []

        for iteration in range(self.max_iterations):
            iter_start = time.time()
            try:
                resp = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    tools=tools if tools else None,
                    temperature=settings.llm_temperature,
                    parallel_tool_calls=settings.agent_parallel_tools,
                )
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                final_text = "抱歉，AI 服务暂时不可用，请稍后重试。"
                trace_steps.append({
                    "iteration": iteration, "step_type": "error",
                    "detail": {"error": str(e)},
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
                    *[self._call_tool(name, args) for _, name, args in tool_tasks],
                    return_exceptions=True,
                )

                messages.append({
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
                })

                for (tc, tool_name, args), result in zip(tool_tasks, results):
                    if isinstance(result, Exception):
                        result_str = json.dumps({"error": str(result)}, ensure_ascii=False)
                    else:
                        result_str = result
                    # 视频工具：当场提取视频数据（不被 300 字符截断影响）
                    if tool_name == "search_recipe_videos" and "error" not in result_str.lower():
                        try:
                            vr = json.loads(result_str)
                            if vr.get("videos"):
                                video_data_list.extend(vr["videos"])
                        except Exception:
                            pass

                    result_summary = result_str[:300]
                    tool_calls_log.append({
                        "tool": tool_name,
                        "args": args,
                        "result": result_summary,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
                    # 追踪每次工具调用
                    trace_steps.append({
                        "iteration": iteration, "step_type": "tool_result",
                        "detail": {
                            "tool": tool_name,
                            "args": {k: str(v)[:100] for k, v in args.items()},
                            "result_summary": result_summary,
                            "is_error": "error" in result_summary.lower(),
                        },
                        "duration_ms": 0,  # 工具调用时间已计入整体
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

        self.history.append(ConversationMessage(role="assistant", content=final_text))

        # ---- 注入视频卡片（数据已在工具调用时提取） ----
        if video_data_list:
            cards = ""
            for v in video_data_list[:3]:
                title = v.get("title", "")
                url = v.get("url", "")
                author = v.get("author", "")
                duration = v.get("duration", "")
                plays = v.get("play_count", "")
                import hashlib
                hue = int(hashlib.md5(title.encode()).hexdigest()[:4], 16) % 360
                emojis = ["🍳","🥘","🍖","🔥","🥩","🐟","🍗","🥬","🍜","🍲","🫕","🧑‍🍳"]
                emoji = emojis[hash(title) % len(emojis)]
                cards += (
                    f'<a class="video-card" href="{url}" target="_blank" rel="noopener">'
                    f'<div class="video-thumb" style="background:linear-gradient(135deg,'
                    f'hsl({hue},70%,45%),hsl({(hue+40)%360},70%,30%))">'
                    f'<span class="video-emoji">{emoji}</span>'
                    f'<span class="video-label">{title[:12]}</span>'
                    f'<span class="video-duration">{duration}</span>'
                    f'</div>'
                    f'<div class="video-meta">'
                    f'<span class="video-title">{title[:40]}</span>'
                    f'<span class="video-info">B站 · {author} · {plays}播放</span>'
                    f'</div>'
                    f'</a>'
                )
            final_text += f'<!--VIDEOS--><div class="video-cards">{cards}</div><!--/VIDEOS-->'

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
        """流式执行 ReAct 循环（含滑动窗口摘要，历史 <= 3000 tokens）"""
        self._current_user_id = request.user_id
        self.history.append(ConversationMessage(role="user", content=request.message))
        tools = ToolRegistry.list_tools(self.tool_names)
        profile_text = ""
        profile = request.context.get("profile")
        if profile:
            parts = []
            if profile.get("name"):
                parts.append(f"用户姓名: {profile['name']}")
            parts.append(f"家庭成员: {profile.get('family_size', '')}人")
            if profile.get("dietary_preferences"):
                parts.append(f"饮食偏好: {', '.join(profile['dietary_preferences'])}")
            if profile.get("allergies"):
                parts.append(f"过敏物: {', '.join(profile['allergies'])}")
            if profile.get("disliked_foods"):
                parts.append(f"忌口: {', '.join(profile['disliked_foods'])}")
            if profile.get("budget_monthly"):
                parts.append(f"月度预算: {profile['budget_monthly']}元")
            profile_text = " | ".join(parts)
        full_prompt = (
            f"{self.system_prompt}\n\n"
            + (f"[用户档案] {profile_text}\n" if profile_text else "")
            + f"用户ID: {request.user_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        messages = [{"role": "system", "content": full_prompt}]

        # 滑动窗口摘要：保留最近 5 轮原文，更早的自动压缩为摘要
        MAX_FULL = 5  # 保留原文的轮数
        MAX_HISTORY_TOKENS = 3000
        if len(self.history) > MAX_FULL:
            try:
                old_text = "\n".join(
                    f"{'用户' if h.role == 'user' else '助手'}: {h.content[:200]}"
                    for h in self.history[:-MAX_FULL][-20:]
                )
                summary = await self._summarize_history(old_text)
                if summary:
                    messages.append({"role": "system", "content": f"[历史对话摘要] {summary}"})
            except Exception:
                pass
        for h in self.history[-MAX_FULL:]:
            messages.append({"role": h.role, "content": h.content})

        full_text = ""
        video_results: list[dict] = []  # 收集视频搜索结果
        for _ in range(self.max_iterations):
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=tools if tools else None,
                temperature=settings.llm_temperature,
                stream=True,
            )

            chunks = []
            tool_call_chunks: dict[int, dict] = {}
            async for chunk in resp:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                if delta.content:
                    chunks.append(delta.content)
                    yield delta.content
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

            content_text = "".join(chunks)

            if content_text and not tool_call_chunks:
                full_text = content_text
                break

            if tool_call_chunks:
                yield "\n\n"
                for idx, tc_data in tool_call_chunks.items():
                    tool_name = tc_data["name"]
                    try:
                        args = json.loads(tc_data["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    tool_result = await self._call_tool(tool_name, args)
                    # 捕获视频搜索结果
                    if tool_name == "search_recipe_videos" and "error" not in tool_result.lower():
                        try:
                            vr = json.loads(tool_result)
                            if vr.get("videos"):
                                video_results.extend(vr["videos"])
                        except Exception:
                            pass
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tc_data["id"] or f"call_{idx}",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": tc_data["arguments"]}
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_data["id"] or f"call_{idx}",
                        "content": tool_result,
                    })
                continue

            if content_text:
                full_text = content_text
                break
            break

        if not full_text:
            full_text = "处理完成。"
            yield full_text

        # 追加视频卡片
        if video_results:
            cards = ""
            for v in video_results[:3]:
                thumb = v.get("thumbnail", "")
                title = v.get("title", "")
                url = v.get("url", "")
                author = v.get("author", "")
                duration = v.get("duration", "")
                plays = v.get("play_count", "")
                # 用菜名哈希生成稳定的渐变色 + emoji 封面
                import hashlib
                hue = int(hashlib.md5(title.encode()).hexdigest()[:4], 16) % 360
                emojis = ["🍳","🥘","🍖","🔥","🥩","🐟","🍗","🥬","🍜","🍲","🫕","🧑‍🍳"]
                emoji = emojis[hash(title) % len(emojis)]
                cards += (
                    f'<a class="video-card" href="{url}" target="_blank" rel="noopener">'
                    f'<div class="video-thumb" style="background:linear-gradient(135deg,'
                    f'hsl({hue},70%,45%),hsl({(hue+40)%360},70%,30%))">'
                    f'<span class="video-emoji">{emoji}</span>'
                    f'<span class="video-label">{title[:12]}</span>'
                    f'<span class="video-duration">{duration}</span>'
                    f'</div>'
                    f'<div class="video-meta">'
                    f'<span class="video-title">{title[:40]}</span>'
                    f'<span class="video-info">B站 · {author} · {plays}播放</span>'
                    f'</div>'
                    f'</a>'
                )
            video_html = f'<!--VIDEOS--><div class="video-cards">{cards}</div><!--/VIDEOS-->'
            full_text += video_html
            yield video_html  # 作为最后一个 chunk 推送

        self.history.append(ConversationMessage(role="assistant", content=full_text))

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

    def clear_history(self):
        self.history.clear()


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
        track_packages, get_community_notices, get_family_schedule,
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
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("get_elderly_activity", get_elderly_activity,
        "查看老人活动状态和今日活动规律",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})

    # Household tools
    ToolRegistry.register("track_packages", track_packages,
        "追踪在途快递包裹状态",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("get_community_notices", get_community_notices,
        "获取社区通知和近期活动",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
    ToolRegistry.register("get_family_schedule", get_family_schedule,
        "获取家庭日程总览（所有成员）",
        {"type":"object","properties":{"user_id":{"type":"string"},"days":{"type":"integer"}},"required":["user_id"]})

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
        {"type":"object","properties":{"user_id":{"type":"string"},"appliance_id":{"type":"string"},"action":{"type":"string"}},"required":["user_id","appliance_id","action"]})
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
        {"type":"object","properties":{"user_id":{"type":"string"},"task_id":{"type":"string"},"contact":{"type":"string"}},"required":["user_id","task_id"]})
    ToolRegistry.register("send_notification", send_notification,
        "向用户发送通知（App推送/短信/邮件）",
        {"type":"object","properties":{"user_id":{"type":"string"},"title":{"type":"string"},"body":{"type":"string"},"channel":{"type":"string"},"priority":{"type":"string"}},"required":["user_id","title","body"]})
    ToolRegistry.register("send_bill_reminder", send_bill_reminder,
        "检查水电煤物业宽带账单，自动发送缴费提醒",
        {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]})
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