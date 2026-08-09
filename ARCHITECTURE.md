# 🏠 Agent of Life v5.5 — 全局业务逻辑树状图

> Self-built ReAct + BGE-M3 + 6大领域统一Agent
> 总计: 47个Python源文件 | 40+工具函数 | 9个数据库表 | 5个API路由模块 | 4阶段RAG流水线

---

## 【入口层】 backend/app/main.py

```
📦 FastAPI app
   │
   ├─ @asynccontextmanager lifespan()              ← 启动/关闭生命周期
   │    │
   │    ├─ logger.info()                              ← 打印启动信息
   │    │
   │    ├─ [启动] .agents.base_agent.register_all_tools()  ← 注册40+工具到ToolRegistry
   │    │
   │    ├─ [启动] .models.database.init_db()              ← 创建PostgreSQL全部表
   │    │
   │    ├─ [启动] .services.scheduler_service.get_scheduler() ← 启动调度器
   │    │
   │    ├─ [后台] asyncio.create_task(_index_recipes_bg())
   │    │    │
   │    │    ├─ .tools.recipe_tools.index_recipes_to_vectordb()
   │    │    │    → BGE-M3.encode(50+道菜谱) → Qdrant.upsert (语义搜索就绪)
   │    │    │
   │    │    └─ .tools.recipe_tools.index_knowledge_to_vectordb()
   │    │         → BGE-M3.encode(8篇家电保养知识) → Qdrant.upsert
   │    │
   │    └─ [关闭] .memory.conversation_memory.get_conversation_memory().close()
   │         → 关闭 Redis 连接
   │
   ├─ app.mount("/static", StaticFiles)               ← 前端静态资源
   │
   ├─ @app.get("/")          root()                   ← API 根信息
   ├─ @app.get("/favicon.ico") favicon()              ← 网站图标
   ├─ @app.get("/health")    health()                 ← 健康检查
   │
   ├─ @app.exception_handler(Exception) global_exception_handler()
   │
   └─ middleware: CORS + RateLimiting(slowapi) + OpenTelemetry(可选)
```
