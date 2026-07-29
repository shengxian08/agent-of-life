"""
Agent of Life — FastAPI Entry Point v5.5
Self-built ReAct Agent + BGE-M3 Hybrid RAG (4-stage) + loguru logging
"""
import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from .config import settings

# ---- Rate Limiting ----
_rate_limiter = None
if settings.rate_limit_enabled:
    try:
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        _rate_limiter = Limiter(key_func=get_remote_address)
    except ImportError:
        pass

# ---- Logging Setup ----
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level=settings.log_level,
    colorize=True,
)
logger.add(
    settings.data_dir / "logs" / "agent_{time:YYYY-MM-DD}.log",
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
)

from .api.routes import routers

# ---- OpenTelemetry (optional) ----
if settings.otel_enabled:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter())
        )
        trace.set_tracer_provider(provider)
        OTEL_READY = True
        logger.info("OpenTelemetry tracing enabled")
    except ImportError:
        OTEL_READY = False
        logger.debug("opentelemetry packages not installed, tracing disabled")
    except Exception as e:
        OTEL_READY = False
        logger.warning(f"OpenTelemetry init failed: {e}")
else:
    OTEL_READY = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("=" * 60)
    logger.info(f"  {settings.app_name} v{settings.app_version}")
    logger.info(f"  Agent: Unified (single agent, 40+ tools, all 6 domains)")
    logger.info(f"  LLM: {settings.openai_model} @ {settings.openai_base_url}")
    logger.info(f"  Embedding: {settings.embedding_model_name}")
    logger.info(f"  RAG: Qdrant + Hybrid (Dense+BM25+RRF) + BGE-Reranker")
    logger.info(f"  Engine: Self-built ReAct loop (not LangChain/LangGraph)")
    logger.info("=" * 60)

    # Register tools
    from .agents.base_agent import register_all_tools
    register_all_tools()
    logger.success("20+ tools registered")

    # Init database
    from .models.database import init_db
    await init_db()
    logger.success("Database initialized")

    # Start scheduler
    from .services.scheduler_service import get_scheduler
    get_scheduler()
    logger.success("Scheduler started")

    # Index recipes into Qdrant for semantic search (background)
    asyncio.create_task(_index_recipes_bg())
    logger.info("Recipe indexing triggered (background)")

    yield

    # Shutdown
    logger.info("Application shutting down...")
    from .memory.conversation_memory import get_conversation_memory
    memory = get_conversation_memory()
    await memory.close()


async def _index_recipes_bg():
    """Background task: index recipes + household knowledge into Qdrant"""
    await asyncio.sleep(5)  # 等 BGE-M3 模型加载完
    try:
        from .tools.recipe_tools import index_recipes_to_vectordb, index_knowledge_to_vectordb
        recipe_count = await index_recipes_to_vectordb()
        if recipe_count > 0:
            logger.success(f"Recipe indexing complete: {recipe_count} recipes indexed")
        else:
            logger.debug("Recipes already indexed, skipped")

        knowledge_count = await index_knowledge_to_vectordb()
        if knowledge_count > 0:
            logger.success(f"Knowledge indexing complete: {knowledge_count} docs indexed")
        else:
            logger.debug("Knowledge already indexed, skipped")
    except Exception as e:
        logger.warning(f"Indexing skipped (model not ready): {e}")


async def _startup_check():
    try:
        from .services.scheduler_service import get_scheduler
        await get_scheduler().run_daily_checkup()
        logger.success("Startup check complete")
    except Exception as e:
        logger.warning(f"Startup check skipped: {e}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "LLM-powered Household AI Agent v5.5 — "
        "Single Unified Agent with 40+ tools, covering Shopping / Meal Planning / "
        "Appliance Control / Maintenance / Security / Household Affairs. "
        "Powered by Self-built ReAct + BGE-M3 + Hybrid RAG (4-stage)."
    ),
    lifespan=lifespan,
)

# CORS — 生产环境通过 CORS_ALLOWED_ORIGINS 环境变量限制
cors_origins = settings.cors_allowed_origins
allow_origins = (
    [o.strip() for o in cors_origins.split(",") if o.strip()]
    if cors_origins != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=cors_origins != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in routers:
    app.include_router(router, prefix="/api/v1")

# OpenTelemetry instrumentation
if OTEL_READY:
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

# Apply rate limiting to app
if _rate_limiter:
    app.state.limiter = _rate_limiter
    from slowapi.middleware import SlowAPIMiddleware
    app.add_middleware(SlowAPIMiddleware)
    logger.info(f"Rate limiting enabled: {settings.rate_limit_requests}/{settings.rate_limit_window_seconds}s")


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "llm": settings.openai_model,
        "embedding": settings.embedding_model_name,
        "reranker": settings.reranker_model_name if settings.use_reranker else "disabled",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/v1/agent/chat",
            "chat_stream": "/api/v1/agent/chat/stream",
            "workflows": "/api/v1/agent/workflow/{type}",
            "alerts": "/api/v1/dashboard/alerts",
            "db_tables": "/api/v1/db/tables",
        },
        "tech_stack": {
            "agent_architecture": "Self-built ReAct Loop + Function Calling (not LangChain/LangGraph)",
            "rag": "4-Stage Hybrid Retrieval (Query Rewrite → Dense+BM25 → RRF → BGE-Reranker)",
            "memory": "Redis + Qdrant + LLM Summarization + Auto Preference Extraction",
            "embedding": settings.embedding_model_name,
        },
    }


@app.get("/favicon.ico")
async def favicon():
    import os
    favicon_path = os.path.join(frontend_dir, "favicon.png")
    if os.path.exists(favicon_path):
        from fastapi.responses import FileResponse
        return FileResponse(favicon_path, media_type="image/png")
    return {"detail": "Not Found"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.app_name, "version": settings.app_version}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__},
    )


# ---- Frontend ----
import os
frontend_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)
if os.path.exists(frontend_dir):
    @app.get("/app")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    try:
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level=settings.log_level.lower(),
    )