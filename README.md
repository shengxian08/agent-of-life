# 🏠 家务事务全权代办 Agent (Agent of Life)

> AI Agent 自动管理全家事务：购物、菜谱、家电、维保

## 功能模块

| 模块 | 功能 | Agent |
|------|------|-------|
| 🛒 购物管理 | 冰箱库存、购物清单、商超比价 | ShoppingAgent |
| 🍳 膳食规划 | 一周菜谱、食材匹配、做法查询 | MealPlannerAgent |
| ⚡ 家电调度 | 错峰预约、智能控制、电费节省 | ApplianceAgent |
| 🔧 维保管理 | 保养检查、维修联系、缴费提醒 | MaintenanceAgent |

## 技术架构

```
┌──────────────────────────────────────┐
│         Frontend (HTML/JS)           │
├──────────────────────────────────────┤
│    FastAPI Gateway (Port 8000)       │
├──────────────────────────────────────┤
│         Orchestrator Agent           │
│  ┌────────┬────────┬────────┬──────┐ │
│  │Shopping│  Meal  │Appliance│ Maint│ │
│  │ Agent  │ Agent  │  Agent  │ Agent│ │
│  └────────┴────────┴────────┴──────┘ │
├──────────────────────────────────────┤
│  Tools | Memory | RAG | Crawlers     │
├──────────────────────────────────────┤
│  SQLite/MySQL | Redis | ChromaDB     │
└──────────────────────────────────────┘
```

## 快速启动

### 1. 安装依赖
```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置环境
```bash
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY
```

### 3. 启动服务
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问
- **API 文档**: http://localhost:8000/docs
- **前端界面**: http://localhost:8000/app
- **API 入口**: http://localhost:8000/api/v1/agent/chat

### Docker 启动
```bash
docker-compose up -d
```

## API 接口

### Agent 对话
```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","user_id":"user_001","message":"帮我规划一周菜谱"}'
```

### 冰箱库存
```bash
curl http://localhost:8000/api/v1/shopping/fridge/user_001
```

### 错峰预约
```bash
curl -X POST http://localhost:8000/api/v1/appliance/off-peak/user_001 \
  -H "Content-Type: application/json" -d '{"date_str":""}'
```

## 项目结构
```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py             # 配置管理
│   ├── api/                  # API 路由
│   │   ├── deps.py
│   │   └── routes/
│   ├── agents/               # Agent 层
│   │   ├── base_agent.py     # ReAct 基类 + ToolRegistry
│   │   ├── orchestrator.py   # 主协调器
│   │   ├── shopping_agent.py
│   │   ├── meal_planner_agent.py
│   │   ├── appliance_agent.py
│   │   ├── maintenance_agent.py
│   │   └── crew.py           # 多Agent协作
│   ├── tools/                # 工具层
│   │   ├── shopping_tools.py
│   │   ├── recipe_tools.py
│   │   ├── appliance_tools.py
│   │   ├── maintenance_tools.py
│   │   ├── notification_tools.py
│   │   └── calendar_tools.py
│   ├── memory/               # 记忆系统
│   │   ├── vector_store.py   # ChromaDB
│   │   ├── conversation_memory.py
│   │   └── user_profile.py
│   ├── rag/                  # RAG 检索增强
│   │   ├── chunker.py
│   │   ├── embeddings.py
│   │   ├── retriever.py
│   │   └── qa_chain.py
│   ├── models/               # 数据模型
│   │   ├── schemas.py        # Pydantic
│   │   └── database.py       # SQLAlchemy
│   └── crawlers/             # 爬虫
│       └── supermarket.py
├── frontend/                 # 前端界面
├── Dockerfile
└── requirements.txt
```

## 使用的技术

- **Python 异步** (asyncio, FastAPI)
- **Pydantic** 数据校验
- **ReAct/Plan** Agent 架构
- **Function Calling** 工具调用
- **CrewAI** 风格多Agent协作
- **ChromaDB** 向量存储 (RAG)
- **Redis** 短期记忆
- **SQLAlchemy** ORM (SQLite/MySQL)
- **Playwright** 爬虫
- **Docker** 容器化

## 开发者

Codex 别小瞧我们！🐱‍👤
