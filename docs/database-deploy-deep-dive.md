# Agent of Life - 数据库与部署深度解析

> 10张PostgreSQL表 + Docker三容器编排 + 50+配置项
> 核心文件: database.py(223行) / config.py(163行) / Dockerfile(40行) / docker-compose.yml(54行)

---

## 目录

1. [数据库层](#1-数据库层)
   - 1.1 10张表全景
   - 1.2 业务表详解
   - 1.3 可观测性表详解
   - 1.4 异步引擎与会话管理
   - 1.5 Pydantic校验层
2. [配置系统](#2-配置系统)
   - 2.1 配置分类全景
   - 2.2 配置加载机制
3. [Docker部署](#3-docker部署)
   - 3.1 开发环境 (docker-compose.yml)
   - 3.2 生产环境 (docker-compose.prod.yml)
   - 3.3 Dockerfile 多阶段构建
4. [运维工具](#4-运维工具)
   - 4.1 Makefile命令速查
   - 4.2 环境变量模板

---

## 1. 数据库层

文件: models/database.py (223行) + models/schemas.py (409行)

### 1.1 10张表全景

```
PostgreSQL (household)
  |
  ├── users             用户账号 + 偏好 + 预算 + 地址
  ├── fridge_items      冰箱库存 (外键->users)
  ├── shopping_records  购物历史记录 (外键->users)
  ├── meal_plans        菜谱周计划 (外键->users)
  ├── appliances        家电信息 (外键->users)
  ├── maintenance_tasks 维保/维修任务 (外键->users)
  ├── tracking_numbers  快递单号 (外键->users)
  │
  ├── agent_traces      Agent执行全链路追踪
  ├── user_feedback     用户反馈 (赞/踩+原因)
  └── token_usage       LLM Token用量 + 费用统计
```

两类表:
- 业务表 (7张): 存储用户数据和业务状态, 带外键约束
- 可观测性表 (3张): 存储Agent运行数据, 用于追踪/反馈/费用分析

### 1.2 业务表详解

**users** - 用户画像

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | String(64) PK | 用户唯一标识 |
| name | String(100) | 用户昵称 |
| password_hash | String(256) | bcrypt加密密码 |
| email | String(200) | 邮箱(登录用) |
| family_size | Integer | 家庭人数 (默认1) |
| dietary_preferences | JSON | 饮食偏好列表 |
| allergies | JSON | 过敏物列表 |
| disliked_foods | JSON | 忌口列表 |
| budget_monthly | Float | 月度预算 (默认3000) |
| preferred_supermarkets | JSON | 偏好超市列表 |
| city | String(50) | 城市 (默认北京) |
| location | String(100) | 区域 (默认朝阳区) |
| created_at | DateTime | 注册时间 |
| last_login | DateTime | 最后登录时间 |

**fridge_items** - 冰箱库存 (外键->users)

| 字段 | 类型 | 说明 |
|------|------|------|
| item_id | String(64) PK | 物品ID |
| user_id | String(64) FK | 所属用户 |
| name | String(120) | 食材名 |
| category | String(50) | 分类 (蔬菜/水果/肉类...) |
| quantity | Float | 数量 |
| unit | String(20) | 单位 (个/斤/kg...) |
| purchase_date | Date | 购买日期 |
| expiry_date | Date | 过期日期 |
| storage_location | String(50) | 存放位置 (冷藏/冷冻/常温) |
| price | Float | 购买价格 |
| calories_per_unit | Float | 单位热量 |
| protein_per_unit | Float | 单位蛋白质 |
| fat_per_unit | Float | 单位脂肪 |
| carbs_per_unit | Float | 单位碳水 |

**shopping_records** - 购物记录 (外键->users)

| 字段 | 类型 | 说明 |
|------|------|------|
| record_id | String(64) PK | 记录ID |
| user_id | String(64) FK | 所属用户 |
| list_id | String(64) | 关联购物清单ID |
| supermarket | String(100) | 超市名称 |
| total_cost | Float | 总花费 |
| items | JSON | 购买物品列表 (JSON数组) |
| purchased_at | DateTime | 购买时间 |

**meal_plans** - 菜谱周计划 (外键->users)

| 字段 | 类型 | 说明 |
|------|------|------|
| plan_id | String(64) PK | 计划ID |
| user_id | String(64) FK | 所属用户 |
| start_date | Date | 计划开始日期 |
| end_date | Date | 计划结束日期 |
| meals | JSON | 每日三餐安排 (JSON对象) |
| generated_at | DateTime | 生成时间 |

**appliances** - 家电信息 (外键->users)

| 字段 | 类型 | 说明 |
|------|------|------|
| appliance_id | String(64) PK | 家电ID |
| user_id | String(64) FK | 所属用户 |
| name | String(100) | 家电名称 |
| appliance_type | String(50) | 类型 (robot_vacuum/washing_machine...) |
| brand | String(50) | 品牌 |
| model | String(50) | 型号 |
| purchase_date | Date | 购买日期 |
| warranty_expiry | Date | 保修到期日 |
| maintenance_cycle_days | Integer | 维保周期 (默认180天) |
| is_smart | Integer | 是否智能 (0/1) |
| off_peak_only | Integer | 仅错峰运行 (0/1) |

**maintenance_tasks** - 维保任务 (外键->users)

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | String(64) PK | 任务ID |
| user_id | String(64) FK | 所属用户 |
| appliance_id | String(64) | 关联家电 |
| appliance_name | String(100) | 家电名称 |
| task_type | String(50) | 任务类型 (cleaning/repair/inspection...) |
| description | Text | 任务描述 |
| priority | String(20) | 优先级 (low/medium/high/urgent) |
| status | String(20) | 状态 (pending/scheduled/completed...) |
| due_date | Date | 到期日 |
| estimated_cost | Float | 预估费用 |
| service_contact | String(100) | 维修师傅电话 |

**tracking_numbers** - 快递单号 (外键->users)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增ID |
| user_id | String(64) FK | 所属用户 |
| tracking_id | String(64) | 快递单号 |
| carrier | String(32) | 快递公司 (默认顺丰) |
| description | String(200) | 备注 |
| created_at | DateTime | 录入时间 |

### 1.3 可观测性表详解

**agent_traces** - Agent执行全链路追踪

| 字段 | 类型 | 说明 |
|------|------|------|
| trace_id | String(64) PK | 追踪ID |
| session_id | String(64) INDEX | 会话ID |
| user_id | String(64) INDEX | 用户ID |
| agent_name | String(64) | Agent名称 (unified) |
| intent | String(32) | 意图分类 |
| user_message | Text | 用户原始消息 |
| iteration | Integer | ReAct第几轮 |
| step_type | String(32) | 步骤类型 (llm_call/tool_result/final/error) |
| detail | JSON | 详情 (工具名/参数/结果/token数) |
| duration_ms | Integer | 此步耗时(毫秒) |
| created_at | DateTime | 时间戳 |

每条ReAct迭代可能产生3-5条trace记录 (llm_call + tool_result x N)。一个会话可能产生十几条。

**user_feedback** - 用户反馈

| 字段 | 类型 | 说明 |
|------|------|------|
| feedback_id | String(64) PK | 反馈ID |
| session_id | String(64) INDEX | 会话ID |
| user_id | String(64) INDEX | 用户ID |
| trace_id | String(64) | 关联追踪 (可选) |
| user_message | Text | 对应的用户消息 |
| agent_response | Text | 对应的AI回复 |
| rating | String(16) | 评价 (positive/negative/neutral) |
| comment | Text | 补充说明 |

**token_usage** - Token用量+费用统计

| 字段 | 类型 | 说明 |
|------|------|------|
| record_id | String(64) PK | 记录ID |
| user_id | String(64) INDEX | 用户ID |
| session_id | String(64) | 会话ID |
| model | String(64) | 模型名称 (deepseek-chat...) |
| prompt_tokens | Integer | 输入token数 |
| completion_tokens | Integer | 输出token数 |
| total_tokens | Integer | 总token数 |
| estimated_cost_cny | Float | 估算费用(元) |
| endpoint | String(128) | API端点 (/api/v1/agent/chat) |

费用计算公式: cost = prompt/1M * prompt_price + completion/1M * completion_price
DeepSeek价格: deepseek-chat: prompt 1元/1M, completion 2元/1M; deepseek-reasoner: prompt 4元/1M, completion 16元/1M

### 1.4 异步引擎与会话管理

```python
# 全局单例引擎
_engine = create_async_engine(
    database_url,         # postgresql+asyncpg://...
    pool_size=10,         # 常驻连接池
    max_overflow=20,      # 溢出连接
    pool_recycle=3600,    # 连接回收 (1小时)
)
_async_session_maker = async_sessionmaker(_engine, expire_on_commit=False)

# 启动时建表
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # 自动建表, 已有则跳过

# 依赖注入: 每次请求获取独立会话
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _async_session_maker() as session:
        yield session  # 请求结束自动 close
```

注意: 使用 create_all 自动建表, 无 Alembic 迁移。适合个人/小团队项目。

### 1.5 Pydantic 校验层

文件: models/schemas.py (409行)

两层校验:

**请求校验**: AgentRequest (session_id, user_id, message, intent, confirmed_tools), LoginRequest, RegisterRequest, FeedbackRequest
**响应校验**: AgentResponse (session_id, response, intent, tool_calls, confidence, requires_confirmation), TokenResponse
**业务模型**: UserProfile, FridgeItem, Recipe, ShoppingList, MealPlan, Appliance, MaintenanceTask, 等15+个模型

关键: AgentResponse.requires_confirmation + pending_dangerous_calls 承载安全护栏的确认回传。

---

## 2. 配置系统

文件: config.py (163行)

### 2.1 配置分类全景 (50+ 配置项)

| 分类 | 配置项数 | 关键配置 |
|------|:--:|------|
| LLM | 4 | openai_api_key, openai_base_url, openai_model, temperature |
| Vision | 4 | vision_enabled, vision_model, vision_base_url, vision_api_key |
| Embedding | 3 | embedding_model_name, embedding_device, embedding_dim(1024) |
| Reranker | 3 | reranker_model_name, use_reranker, reranker_top_n |
| RAG检索 | 5 | hybrid_alpha(0.7), retrieval_top_k(20), final_top_k(5), min_dense_score(0.35), use_hyde |
| Redis | 2 | redis_url, redis_max_connections |
| Database | 1 | database_url (postgresql+asyncpg://...) |
| Qdrant | 2 | qdrant_url, qdrant_collection |
| App | 4 | app_host, app_port(8000), app_debug, app_name, app_version(5.5.0) |
| Auth | 3 | jwt_secret, jwt_algorithm(HS256), jwt_expire_minutes(1440) |
| Agent | 4 | agent_max_iterations(10), max_tool_calls(8), parallel_tools, history_limit(40) |
| Memory | 2 | consolidation_threshold(6), long_term_ttl_days(90) |
| Household | 5 | 峰谷电时段, 默认城市, 默认区域 |
| External | 2 | kuaidi100_customer, kuaidi100_key |
| Monitoring | 2 | otel_enabled, log_level |
| RateLimit | 3 | rate_limit_enabled, requests(60), window_seconds(60) |
| Security | 1 | cors_allowed_origins |

### 2.2 配置加载机制

```python
class Settings(BaseSettings):
    openai_api_key: SecretStr = Field(
        default=SecretStr('sk-xxx'),       # 硬编码默认值
        alias='OPENAI_API_KEY'             # 环境变量覆盖
    )

    model_config = {
        'env_file': '.env',                # 自动从 .env 文件加载
        'env_file_encoding': 'utf-8',
        'extra': 'ignore',                 # 忽略未定义的额外字段
    }

settings = Settings()  # 全局单例, 启动时实例化
```

优先级: 环境变量 > .env 文件 > 代码默认值。SecretStr 类型保护敏感字段, 需调用 .get_secret_value() 获取原始值。

---

## 3. Docker 部署

### 3.1 开发环境 (docker-compose.yml 54行)

三容器架构:

```
docker compose up -d
  |
  ├── db (postgres:16-alpine)
  │     healthcheck: pg_isready, 5s间隔, 5次重试
  │     port: 5432
  │     volume: pgdata:/var/lib/postgresql/data
  │
  ├── qdrant (qdrant/qdrant:latest)
  │     port: 6333(HTTP) + 6334(gRPC)
  │     volume: qdrant_data:/qdrant/storage
  │
  └── agent-of-life (build: .)
        port: 8000 -> 8000
        volume: ./backend/data -> /app/backend/data (模型文件持久化)
        depends_on: db(healthy) + qdrant(started)
        env: DATABASE_URL(指向db服务) + QDRANT_URL(指向qdrant服务) + OPENAI_*
```

依赖顺序: agent-of-life 等 db 健康检查通过 + qdrant 启动后才启动。

### 3.2 生产环境 (docker-compose.prod.yml 66行)

与开发环境的区别:

| 维度 | 开发环境 | 生产环境 |
|------|------|------|
| 端口 | 8000:8000 | 80:8000 (标准HTTP) |
| Qdrant端口 | 暴露6333+6334 | 不暴露 (仅内部) |
| DB端口 | 暴露5432 | 不暴露 (仅内部) |
| Redis | 无 (可选) | 有 (redis:7-alpine, 用于记忆持久化) |
| BGE-M3 | 默认路径 | 强制 ./data/models/bge-m3-local |
| Reranker | 默认False | 显式 false (省资源) |
| DEBUG | true | false |
| CORS | * | 通过环境变量限制 |
| 数据卷 | 2个 | 3个 (多一个app_data) |

### 3.3 Dockerfile 多阶段构建 (40行)

```
Stage 1: Builder (python:3.11-slim)
  -> 安装 gcc (编译依赖)
  -> pip install torch (CPU版, 避免拉2GB CUDA包)
  -> pip install requirements.txt (使用阿里云PyPI镜像)

Stage 2: Runtime (python:3.11-slim)
  -> 安装 libgomp1 (torch运行时依赖)
  -> COPY --from=builder pip包 (不包含gcc)
  -> COPY 代码
  -> EXPOSE 8000
  -> CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
```

多阶段构建的好处: 最终镜像不含gcc编译器, 体积更小; torch CPU版避免2GB CUDA依赖。

---

## 4. 运维工具

### 4.1 Makefile 命令速查 (46行)

| 命令 | 作用 |
|------|------|
| make build | 构建Docker镜像 |
| make up | 启动开发环境 (docker compose up -d) |
| make down | 停止所有容器 |
| make restart | 重启所有容器 |
| make logs | 实时查看日志 (docker compose logs -f) |
| make deploy | 准备生产部署 (复制.env.production) |
| make deploy-up | 启动生产环境 (使用prod compose文件) |
| make deploy-down | 停止生产环境 |
| make seed | 填充知识库种子数据 |
| make eval | 运行RAG评估 + 打印4项指标 |
| make seed-and-eval | 种子数据 + 评估一键执行 |
| make clean | 清理日志文件 |

### 4.2 环境变量模板

.env.example (24行) - 开发参考:

| 变量 | 必填 | 说明 |
|------|:--:|------|
| OPENAI_API_KEY | 是 | DeepSeek API Key |
| OPENAI_BASE_URL | 否 | API地址 (默认deepseek) |
| OPENAI_MODEL | 否 | 模型 (默认deepseek-chat) |
| VISION_ENABLED/VISION_MODEL/VISION_API_KEY | 否 | 视觉识别 (千问VL) |
| KUAIDI100_CUSTOMER/KUAIDI100_KEY | 否 | 快递追踪API |
| LOG_LEVEL | 否 | 日志级别 |
| RETRIEVAL_USE_HYDE | 否 | HyDE增强召回 |

.env.production (19行) - 生产必填:

| 变量 | 必填 | 说明 |
|------|:--:|------|
| OPENAI_API_KEY | 是 | DeepSeek API Key |
| JWT_SECRET | 是 | 随机字符串 (加密用户令牌) |
| POSTGRES_PASSWORD | 是 | 数据库密码 (安全起见修改默认值) |

---

## 5. 完整基础设施拓扑

```
                     Internet
                        |
                  ┌─────▼─────┐
                  │   Nginx   │  (可选, 反向代理 + HTTPS)
                  └─────┬─────┘
                        | :80 -> :8000
            ┌───────────▼───────────┐
            │   agent-of-life       │
            │   FastAPI + uvicorn   │
            │   Python 3.11-slim    │
            │                      │
            │  内部依赖:             │
            │  ├── BGE-M3 (本地)    │
            │  ├── DeepSeek (API)   │
            │  └── 千问VL (可选API) │
            └──────┬──────┬────────┘
                   │      │
          ┌────────▼──┐ ┌─▼──────────┐
          │ PostgreSQL │ │   Qdrant   │
          │   :5432    │ │ :6333/6334 │
          │  (业务数据) │ │ (向量存储)  │
          └────────────┘ └────────────┘
                   │
          ┌────────▼──┐
          │   Redis    │  (仅生产环境)
          │   :6379    │  (会话记忆)
          └────────────┘
```

---

## 6. 关键文件索引

| 文件 | 行数 | 职责 |
|------|:--:|------|
| models/database.py | 223 | SQLAlchemy异步模型: 10张表 + 引擎 + 会话 |
| models/schemas.py | 409 | Pydantic校验: 请求/响应/15+业务模型 |
| config.py | 163 | Settings: 50+配置项 + .env自动加载 |
| docker-compose.yml | 54 | 开发环境: 3容器 (db+qdrant+app) |
| docker-compose.prod.yml | 66 | 生产环境: 4容器 (+redis, 封闭端口) |
| Dockerfile | 40 | 多阶段构建: builder + runtime |
| Makefile | 46 | 运维命令: build/up/down/eval/deploy |
| .env.example | 24 | 开发环境变量模板 |
| .env.production | 19 | 生产环境变量模板 |