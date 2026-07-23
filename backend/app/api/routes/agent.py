"""
Agent 对话路由 v5.2 — 普通 + 流式(SSE) + LangGraph + 追踪 + 反馈 + 图片代理
"""
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, Response
from loguru import logger
import httpx

from ...models.schemas import (
    AgentRequest, AgentResponse, FeedbackRequest, TokenStats, TraceSummary,
)
from ...models.database import get_db, FeedbackRecord, TraceRecord, TokenUsageRecord
from ...agents.crew import HouseholdCrew
from ...memory.conversation_memory import ConversationMemory, ConversationMessage
from ...memory.user_profile import UserProfileManager
from ..deps import get_crew, get_memory, get_profile_mgr
from .auth import get_current_user
from sqlalchemy import select, func

router = APIRouter(prefix="/agent", tags=["Agent"])

# Rate limiting: try slowapi, fallback gracefully
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    _limiter = Limiter(key_func=get_remote_address)
except ImportError:
    _limiter = None


@router.post("/chat", response_model=AgentResponse)
async def chat(
    request: AgentRequest,
    crew: HouseholdCrew = Depends(get_crew),
    memory: ConversationMemory = Depends(get_memory),
    profile_mgr: UserProfileManager = Depends(get_profile_mgr),
):
    """Agent 对话（非流式）"""
    profile = await profile_mgr.get_profile(request.user_id)
    if profile:
        request.context["profile"] = profile.model_dump()

    response = await crew.chat(request)

    # Persist to memory (background)
    try:
        await memory.add_message(
            request.session_id,
            ConversationMessage(role="user", content=request.message),
        )
        await memory.add_message(
            request.session_id,
            ConversationMessage(role="assistant", content=response.response),
        )
    except Exception as e:
        logger.warning(f"Memory persist failed: {e}")

    return response


@router.post("/chat/stream")
async def chat_stream(
    request: AgentRequest,
    crew: HouseholdCrew = Depends(get_crew),
    profile_mgr: UserProfileManager = Depends(get_profile_mgr),
):
    """Agent 流式对话（SSE）"""
    profile = await profile_mgr.get_profile(request.user_id)
    if profile:
        request.context["profile"] = profile.model_dump()
    async def event_generator():
        try:
            async for chunk in crew.chat_stream(request):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/chat/graph")
async def chat_graph(
    request: AgentRequest,
    mode: str = Query("langgraph", description="langgraph or crew"),
):
    """LangGraph-powered conversation (experimental)"""
    if mode == "langgraph":
        try:
            from ...agents.graph import run_graph
            result = await run_graph(
                session_id=request.session_id,
                user_id=request.user_id,
                message=request.message,
                thread_id=request.session_id,
            )
            return {
                "session_id": request.session_id,
                "response": result.get("response", ""),
                "intents": result.get("intents", []),
                "confidence": result.get("confidence", 0.0),
                "mode": "langgraph",
            }
        except Exception as e:
            logger.error(f"Graph chat failed: {e}")
            raise HTTPException(500, f"LangGraph error: {str(e)}")
    else:
        from ...agents.crew import get_household_crew
        crew = get_household_crew()
        return await crew.chat_graph(request)


@router.post("/workflow/{workflow_type}")
async def run_workflow(
    workflow_type: str,
    user_id: str,
    session_id: str,
    crew: HouseholdCrew = Depends(get_crew),
):
    """Run predefined workflows with parallel/conditional execution"""
    valid = ["daily_check", "weekly_plan", "evening_routine", "smart_check", "security_check"]
    if workflow_type not in valid:
        raise HTTPException(400, f"Invalid workflow. Choose: {valid}")
    results = await crew.run_workflow(workflow_type, user_id, session_id)
    return {
        "workflow": workflow_type,
        "results": results,
    }


@router.get("/memory/{session_id}")
async def get_memory_context(
    session_id: str,
    limit: int = Query(10, ge=1, le=50),
    memory: ConversationMemory = Depends(get_memory),
):
    """Get conversation memory for a session"""
    history = await memory.get_history(session_id, limit=limit)
    return {
        "session_id": session_id,
        "message_count": len(history),
        "messages": [
            {"role": m.role, "content": m.content[:500], "timestamp": m.timestamp.isoformat()}
            for m in history
        ],
    }


@router.delete("/memory/{session_id}")
async def clear_memory(
    session_id: str,
    memory: ConversationMemory = Depends(get_memory),
):
    """Clear conversation memory for a session"""
    await memory.clear(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.get("/health")
async def health():
    """Agent system health check"""
    graph_status = "unavailable"
    try:
        from ...agents.graph import get_graph_app
        app = get_graph_app()
        graph_status = "ready" if app else "unavailable"
    except Exception:
        pass

    embed_info = {}
    try:
        from ...rag.embeddings import get_embedding_generator
        embed_info = get_embedding_generator().model_info
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "家务事务全权代办 Agent v5.2",
        "agents": ["unified"],
        "domains": ["shopping", "meal_plan", "appliance", "maintenance", "security", "household"],
        "langgraph": graph_status,
        "embedding": embed_info,
    }


# ================================================================
# v5.2 新增: 执行追踪
# ================================================================

@router.get("/trace/{session_id}")
async def get_trace(session_id: str, limit: int = Query(20, ge=1, le=100)):
    """获取某次会话的 Agent 执行追踪"""
    async for session in get_db():
        result = await session.execute(
            select(TraceRecord)
            .where(TraceRecord.session_id == session_id)
            .order_by(TraceRecord.created_at)
            .limit(limit)
        )
        traces = result.scalars().all()
        if not traces:
            return {"session_id": session_id, "traces": [], "message": "无追踪记录"}

        steps = []
        total_duration = 0
        for t in traces:
            steps.append({
                "trace_id": t.trace_id,
                "iteration": t.iteration,
                "step_type": t.step_type,
                "agent_name": t.agent_name,
                "detail": t.detail,
                "duration_ms": t.duration_ms,
                "created_at": t.created_at.isoformat(),
            })
            total_duration += t.duration_ms

        return {
            "session_id": session_id,
            "total_steps": len(steps),
            "total_duration_ms": total_duration,
            "steps": steps,
        }


@router.get("/trace/recent/{user_id}")
async def get_recent_traces(user_id: str, limit: int = Query(10, ge=1, le=50)):
    """获取用户最近的对话追踪"""
    async for session in get_db():
        # 获取最近的 session
        result = await session.execute(
            select(TraceRecord.session_id, func.min(TraceRecord.created_at).label("started_at"))
            .where(TraceRecord.user_id == user_id)
            .group_by(TraceRecord.session_id)
            .order_by(func.min(TraceRecord.created_at).desc())
            .limit(limit)
        )
        rows = result.all()
        sessions_list = []
        for row in rows:
            sid = row[0]
            # 获取此 session 的摘要
            steps_result = await session.execute(
                select(TraceRecord)
                .where(TraceRecord.session_id == sid)
                .order_by(TraceRecord.created_at)
            )
            steps = steps_result.scalars().all()
            if steps:
                first = steps[0]
                last = steps[-1]
                sessions_list.append({
                    "session_id": sid,
                    "user_message": first.detail.get("message", "")[:200],
                    "agent_response": last.detail.get("response", "")[:300],
                    "steps_count": len(steps),
                    "intent": first.intent,
                    "started_at": first.created_at.isoformat(),
                })
        return {"user_id": user_id, "recent_sessions": sessions_list}


# ================================================================
# v5.2 新增: 用户反馈
# ================================================================

@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, user_id: str = Depends(get_current_user)):
    """提交对话反馈"""
    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
    async for session in get_db():
        session.add(FeedbackRecord(
            feedback_id=feedback_id,
            session_id=req.session_id,
            user_id=user_id,
            user_message=req.user_message[:500],
            agent_response=req.agent_response[:2000],
            rating=req.rating,
            comment=req.comment[:500],
        ))
        await session.commit()

    logger.info(f"Feedback [{req.rating}] from {user_id} on session {req.session_id}")
    return {"status": "recorded", "feedback_id": feedback_id, "rating": req.rating}


@router.get("/feedback/stats/{user_id}")
async def get_feedback_stats(user_id: str):
    """获取用户反馈统计"""
    async for session in get_db():
        result = await session.execute(
            select(FeedbackRecord.rating, func.count(FeedbackRecord.rating))
            .where(FeedbackRecord.user_id == user_id)
            .group_by(FeedbackRecord.rating)
        )
        stats = {"positive": 0, "negative": 0, "neutral": 0, "total": 0}
        for rating, count in result.all():
            stats[rating] = count
            stats["total"] += count

        # 最近 10 条反馈
        recent_result = await session.execute(
            select(FeedbackRecord)
            .where(FeedbackRecord.user_id == user_id)
            .order_by(FeedbackRecord.created_at.desc())
            .limit(10)
        )
        recent = []
        for fb in recent_result.scalars().all():
            recent.append({
                "feedback_id": fb.feedback_id,
                "user_message": fb.user_message[:100],
                "agent_response": fb.agent_response[:200],
                "rating": fb.rating,
                "comment": fb.comment,
                "created_at": fb.created_at.isoformat(),
            })

        satisfaction = round(stats["positive"] / max(stats["total"], 1) * 100, 1)
        return {**stats, "satisfaction_rate": satisfaction, "recent": recent}


# ================================================================
# v5.2 新增: Token 用量统计
# ================================================================

@router.get("/tokens/stats/{user_id}")
async def get_token_stats(user_id: str, days: int = Query(30, ge=1, le=365)):
    """获取用户 Token 用量统计"""
    async for session in get_db():
        cutoff = datetime.now().timestamp() - days * 86400
        result = await session.execute(
            select(TokenUsageRecord)
            .where(
                TokenUsageRecord.user_id == user_id,
                TokenUsageRecord.created_at >= datetime.fromtimestamp(cutoff),
            )
        )
        records = result.scalars().all()

        stats = TokenStats()
        stats.calls_count = len(records)
        by_model: dict[str, dict[str, int]] = {}

        for r in records:
            stats.total_prompt_tokens += r.prompt_tokens
            stats.total_completion_tokens += r.completion_tokens
            stats.total_tokens += r.total_tokens
            stats.total_cost_cny += r.estimated_cost_cny

            model = r.model or "unknown"
            if model not in by_model:
                by_model[model] = {"prompt": 0, "completion": 0, "total": 0, "cost": 0, "calls": 0}
            by_model[model]["prompt"] += r.prompt_tokens
            by_model[model]["completion"] += r.completion_tokens
            by_model[model]["total"] += r.total_tokens
            by_model[model]["cost"] += int(r.estimated_cost_cny * 1000)
            by_model[model]["calls"] += 1

        # 把 cost 从分转回元
        for m in by_model:
            by_model[m]["cost"] = round(by_model[m]["cost"] / 1000, 4)

        stats.by_model = by_model
        return stats.model_dump()


@router.get("/tokens/daily/{user_id}")
async def get_daily_tokens(user_id: str, days: int = Query(7, ge=1, le=90)):
    """按天统计 Token 用量"""
    async for session in get_db():
        from sqlalchemy import func as sa_func
        result = await session.execute(
            select(
                sa_func.date(TokenUsageRecord.created_at).label("day"),
                sa_func.sum(TokenUsageRecord.total_tokens).label("tokens"),
                sa_func.sum(TokenUsageRecord.estimated_cost_cny).label("cost"),
                sa_func.count(TokenUsageRecord.record_id).label("calls"),
            )
            .where(
                TokenUsageRecord.user_id == user_id,
                TokenUsageRecord.created_at >= datetime.now().timestamp() - days * 86400,
            )
            .group_by(sa_func.date(TokenUsageRecord.created_at))
            .order_by(sa_func.date(TokenUsageRecord.created_at).desc())
        )
        rows = result.all()
        daily = []
        for row in rows:
            daily.append({
                "date": str(row[0]),
                "tokens": int(row[1] or 0),
                "cost_cny": round(float(row[2] or 0), 4),
                "calls": int(row[3] or 0),
            })
        return {"user_id": user_id, "days": days, "daily": daily}


# ================================================================
# 图片代理 — 解决 B 站封面防盗链（Referrer 限制）
# ================================================================

@router.get("/proxy-image")
async def proxy_image(url: str = Query(...)):
    """代理外部图片，绕过 Referrer 防盗链"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid image URL")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(404, "Image not found")
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )
    except Exception as e:
        logger.warning(f"Image proxy failed: {e}")
        raise HTTPException(502, f"Proxy error: {str(e)[:100]}")