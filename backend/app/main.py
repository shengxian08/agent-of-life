"""
Agent of Life — FastAPI Entry Point v4.0
Upgraded: LangGraph orchestration + BGE-M3 RAG + loguru logging
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
    logger.info(f"  Agent: Unified (all 6 domains in one)")
    logger.info(f"  LLM: {settings.openai_model} @ {settings.openai_base_url}")
    logger.info(f"  Embedding: {settings.embedding_model_name}")
    logger.info(f"  RAG: ChromaDB + Hybrid (Dense+Sparse) + Reranker")
    logger.info(f"  Agent: Semantic Router + LangGraph StateGraph")
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

    # Startup check
    asyncio.create_task(_startup_check())
    logger.info("Startup check triggered (background)")

    # Pre-warm LangGraph (optional)
    try:
        from .agents.graph import get_graph_app
        get_graph_app()
        logger.success("LangGraph graph compiled")
    except Exception as e:
        logger.warning(f"LangGraph not available: {e}")

    # Index recipes into ChromaDB for semantic search (background)
    asyncio.create_task(_index_recipes_bg())
    logger.info("Recipe indexing triggered (background)")

    yield

    # Shutdown
    logger.info("Application shutting down...")
    from .memory.conversation_memory import get_conversation_memory
    memory = get_conversation_memory()
    await memory.close()

    # Cleanup LangGraph resources
    try:
        from .agents.graph import close_graph
        close_graph()
    except Exception:
        pass


async def _index_recipes_bg():
    """Background task: index recipes + household knowledge into ChromaDB"""
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
    """Run initial inspection on startup"""
    await asyncio.sleep(3)
    try:
        from .services.scheduler_service import get_scheduler
        scheduler = get_scheduler()
        result = await scheduler.run_daily_checkup()
        alerts = result.alerts
        if alerts:
            logger.warning(f"Startup check: {len(alerts)} issues found")
            for alert in alerts:
                logger.warning(f"  {alert}")
        else:
            logger.success("Startup check: all clear")
    except Exception as e:
        logger.error(f"Startup check failed: {e}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "LLM-powered Household AI Agent v5.0 — "
        "6-Agent Multi-Agent System: Shopping / Meal Planning / Appliance Control / "
        "Maintenance / Security Monitor / Household Affairs + Automated Workflows. "
        "Powered by LangGraph + BGE-M3 + Hybrid RAG."
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
            "chat_graph": "/api/v1/agent/chat/graph",
            "dashboard": "/api/v1/dashboard/status",
            "workflows": "/api/v1/agent/workflow/{type}",
            "knowledge_search": "/api/v1/knowledge/search",
            "knowledge_ingest": "/api/v1/knowledge/ingest",
        },
        "tech_stack": {
            "agent_orchestration": "LangGraph StateGraph + Semantic Router",
            "rag": "Hybrid Retrieval (Dense+Sparse+RRF) + BGE-M3 + BGE-Reranker",
            "memory": "Redis + ChromaDB + LLM Consolidation",
            "embedding": settings.embedding_model_name,
        },
    }


@app.get("/favicon.ico")
async def favicon():
    import os
    favicon_path = os.path.join(frontend_dir, "favicon.svg")
    if os.path.exists(favicon_path):
        from fastapi.responses import FileResponse
        return FileResponse(favicon_path, media_type="image/svg+xml")
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

    @app.get("/dashboard")
    async def serve_dashboard():
        return FileResponse(os.path.join(frontend_dir, "dashboard.html"))

    @app.get("/database")
    async def serve_database():
        return FileResponse(os.path.join(frontend_dir, "database.html"))

    @app.get("/recommend")
    async def serve_recommend():
        return FileResponse(os.path.join(frontend_dir, "recommend.html"))

    @app.get("/overview")
    async def serve_overview():
        return FileResponse(os.path.join(frontend_dir, "overview.html"))

    @app.get("/memory")
    async def serve_memory():
        return FileResponse(os.path.join(frontend_dir, "memory.html"))

    @app.get("/profile")
    async def serve_profile():
        return FileResponse(os.path.join(frontend_dir, "profile.html"))

    @app.get("/admin")
    async def serve_admin():
        return FileResponse(os.path.join(frontend_dir, "admin.html"))

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