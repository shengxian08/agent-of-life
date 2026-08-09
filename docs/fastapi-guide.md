# ⚡ FastAPI 完全指南

> Python 最快的 Web 框架，没有之一。从 Hello World 到生产级项目。

---

## 目录

1. [FastAPI 是什么？为什么选它？](#1-fastapi-是什么为什么选它)
2. [第一个应用：Hello World](#2-第一个应用hello-world)
3. [路径操作：GET / POST / PUT / DELETE](#3-路径操作get--post--put--delete)
4. [路径参数与查询参数](#4-路径参数与查询参数)
5. [请求体：Pydantic 数据校验](#5-请求体pydantic-数据校验)
6. [响应模型：控制返回什么](#6-响应模型控制返回什么)
7. [依赖注入 Depends — FastAPI 的灵魂](#7-依赖注入-depends--fastapi-的灵魂)
8. [中间件 Middleware](#8-中间件-middleware)
9. [应用生命周期 Lifespan](#9-应用生命周期-lifespan)
10. [异常处理](#10-异常处理)
11. [后台任务 Background Tasks](#11-后台任务-background-tasks)
12. [流式响应 StreamingResponse / SSE](#12-流式响应-streamingresponse--sse)
13. [CORS 跨域配置](#13-cors-跨域配置)
14. [静态文件服务](#14-静态文件服务)
15. [认证与授权 — JWT](#15-认证与授权--jwt)
16. [限流 Rate Limiting](#16-限流-rate-limiting)
17. [自动 API 文档 — Swagger / ReDoc](#17-自动-api-文档--swagger--redoc)
18. [异步支持 — async/await 原生](#18-异步支持--asyncawait-原生)
19. [进阶模式](#19-进阶模式)
20. [本项目实战解析](#20-本项目实战解析)

---

## 1. FastAPI 是什么？为什么选它？

### 一句话

**FastAPI 是 Python 里最快的 Web 框架，利用类型注解自动生成文档、校验数据、提供编辑器提示。**

### 三个核心卖点

```
① 快
   性能对标 Node.js 和 Go（基于 Starlette + Uvicorn）
   比 Flask 快 10 倍，比 Django 快 3 倍

② 爽
   写 Python 类型注解 → 自动校验数据 → 自动生成 API 文档
   编辑器自动补全（VSCode / PyCharm 原生支持）

③ 简洁
   定义一个接口只需要 3 行：
   @app.get("/")
   async def root():
       return {"hello": "world"}
```

### FastAPI vs Flask vs Django

| | FastAPI | Flask | Django |
|------|---------|-------|--------|
| 类型 | 异步框架 | 同步微框架 | 同步全栈框架 |
| 性能 | ⭐⭐⭐⭐⭐ 极快 | ⭐⭐ 慢 | ⭐⭐ 慢 |
| 数据校验 | 自动（Pydantic） | 手动 | 手动（DRF 可以） |
| API 文档 | 自动生成 | 需要插件 | 需要插件 |
| 异步支持 | 原生 async/await | 需要扩展 | 3.1+ 支持 |
| 学习曲线 | 中等 | 简单 | 陡峭 |
| 适合场景 | API 服务、微服务 | 小项目、原型 | 全栈项目、管理后台 |

### 为什么本项目选 FastAPI？

```
项目需求:
  - 40+ 工具，需要大量异步 I/O（数据库、LLM API、向量检索）
  - 流式输出（SSE，打字机效果）
  - API 文档自动生成（方便调试 40+ 个接口）
  - 数据校验（Pydantic 模式，所有输入都要校验）

Flask: 异步需要魔改，数据校验要手写 → 太累
Django: 太重，异步支持不完善 → 不合适
FastAPI: 原生异步 + 自动校验 + 自动文档 → 完美
```

---

## 2. 第一个应用：Hello World

```python
# main.py
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello, {name}!"}
```

### 启动

```bash
# 方式 1: 命令行
uvicorn main:app --reload
#       ↑      ↑      ↑
#    文件名  变量名   热重载（改代码自动重启）

# 方式 2: Python 代码
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

启动后打开：
- `http://localhost:8000` → 你的接口
- `http://localhost:8000/docs` → **自动生成的 Swagger 文档（可以直接在网页上测试接口！）**
- `http://localhost:8000/redoc` → ReDoc 风格的文档

---

## 3. 路径操作：GET / POST / PUT / DELETE

```python
from fastapi import FastAPI

app = FastAPI()


# GET — 读取数据（最常用）
@app.get("/items")
async def list_items():
    return [{"id": 1, "name": "菠菜"}, {"id": 2, "name": "番茄"}]


@app.get("/items/{item_id}")      # 读单个
async def get_item(item_id: int): # ← 自动转为 int
    return {"id": item_id, "name": "菠菜"}


# POST — 创建数据
@app.post("/items")
async def create_item(name: str, price: float):
    return {"id": 3, "name": name, "price": price}


# PUT — 更新数据（完整替换）
@app.put("/items/{item_id}")
async def update_item(item_id: int, name: str, price: float):
    return {"id": item_id, "name": name, "price": price}


# DELETE — 删除数据
@app.delete("/items/{item_id}")
async def delete_item(item_id: int):
    return {"deleted": item_id}
```

### HTTP 方法的语义

| 方法 | 语义 | 幂等性 | 示例 |
|------|------|--------|------|
| GET | 读取 | ✅ 幂等 | 查看冰箱库存 |
| POST | 创建 | ❌ 不幂等 | 添加食材 |
| PUT | 完整替换 | ✅ 幂等 | 修改用户信息 |
| PATCH | 部分更新 | ❌ 不幂等 | 改用户名 |
| DELETE | 删除 | ✅ 幂等 | 清空对话 |

> **幂等** = 执行 1 次和执行 100 次结果一样。

---

## 4. 路径参数与查询参数

```python
# 路径参数 — 在 URL 路径里
# /users/123/orders/456
@app.get("/users/{user_id}/orders/{order_id}")
async def get_order(user_id: int, order_id: int):
    return {"user": user_id, "order": order_id}


# 查询参数 — 在 URL ? 后面
# /search?q=菠菜&limit=10&sort=price
@app.get("/search")
async def search(
    q: str,                          # 必填
    limit: int = 10,                 # 有默认值 → 可选
    sort: str | None = None,         # None → 可选
    include_out_of_stock: bool = False,
):
    return {
        "query": q,
        "limit": limit,
        "sort": sort,
        "include_out_of_stock": include_out_of_stock,
    }


# 混合使用
# /items/5?category=蔬菜&max_price=20
@app.get("/items/{item_id}")
async def get_filtered(
    item_id: int,               # 路径参数（必填）
    category: str | None = None, # 查询参数（可选）
    max_price: float | None = None,
):
    return {"id": item_id, "category": category, "max_price": max_price}
```

### 参数来源一目了然

```
URL: /users/123/orders?status=shipped&page=1

    路径参数: user_id=123  ← /users/{user_id}
    查询参数: status=shipped, page=1  ← ?后面
```

---

## 5. 请求体：Pydantic 数据校验

这是 FastAPI 最漂亮的部分：**用 Python 类定义数据结构，自动校验输入**。

```python
from pydantic import BaseModel, Field, field_validator


# ① 定义数据模型
class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)  # ... 表示必填
    email: str
    age: int = Field(ge=0, le=150)                       # >=0, <=150
    family_size: int = Field(default=1, ge=1, le=20)     # 默认值+约束
    allergies: list[str] = []                             # 默认空列表
    budget: float = Field(default=3000.0, ge=0)

    # 自定义校验器
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("邮箱格式不正确")
        return v.lower()


# ② 接口中使用
@app.post("/users")
async def create_user(user: CreateUserRequest):   # ← 自动校验！
    # user 已经是校验过的 CreateUserRequest 对象
    return {
        "id": "u123",
        "name": user.name,
        "email": user.email,
    }
```

### Pydantic 的校验能力

```python
class Product(BaseModel):
    name: str = Field(..., min_length=1)
    price: float = Field(ge=0.01)          # >= 0.01
    quantity: int = Field(ge=0, le=99999)
    tags: list[str] = Field(default_factory=list, max_length=10)
    category: str = Field(default="其他")

# 自动生成的 API 文档会显示:
#   name: string (required, minLength: 1)
#   price: number (required, >= 0.01)
#   quantity: integer (>= 0, <= 99999)
#   tags: string[] (maxItems: 10)
#   category: string (default: "其他")
```

### 常见 Field 约束

```python
Field(default=...,)         # 必填
Field(default=42)           # 默认值
Field(ge=0, le=100)         # 数值范围
Field(min_length=1, max_length=100)  # 字符串长度
Field(max_length=50)        # 列表最大长度
Field(pattern=r"^\d{11}$")  # 正则匹配（手机号）
Field(gt=0)                 # 大于（不含等于），lt=小于
```

---

## 6. 响应模型：控制返回什么

```python
from pydantic import BaseModel

# 输入模型 — 用户发来的数据
class CreateUserRequest(BaseModel):
    name: str
    email: str
    password: str       # 包含敏感字段


# 输出模型 — 返回给用户的数据（不包含密码！）
class UserResponse(BaseModel):
    id: str
    name: str
    email: str


# response_model 控制返回格式
@app.post("/users", response_model=UserResponse)
async def create_user(user: CreateUserRequest):
    # 内部可能创建了完整用户对象（含密码）
    full_user = {
        "id": "u123",
        "name": user.name,
        "email": user.email,
        "password": "hashed_xxx",  # 这个不会返回！
    }
    return full_user
    # FastAPI 自动过滤，只返回 response_model 里有的字段
```

**为什么重要？**
- 密码永远不会泄露到响应中
- 内部使用的字段（如 `created_at`、`_internal_id`）不会暴露
- 可以给不同接口定义不同的响应模型

---

## 7. 依赖注入 Depends — FastAPI 的灵魂

这是 FastAPI 区别于其他框架的核心特性。

### 7.1 基本概念

```python
from fastapi import FastAPI, Depends

app = FastAPI()


# ① 定义一个"依赖" — 一个返回值的函数
async def get_db():
    """获取数据库连接"""
    db = Database("postgresql://...")
    try:
        yield db          # ← 比 return 更强：可以在用完后清理
    finally:
        await db.close()


# ② 在接口中使用 — FastAPI 自动调用 get_db() 并传入 db
@app.get("/items")
async def list_items(db = Depends(get_db)):  # ← 声明依赖
    items = await db.query("SELECT * FROM items")
    return items
```

### 7.2 依赖的链式调用

```python
# 依赖可以依赖其他依赖（链式注入）

async def get_token(authorization: str = Header(...)) -> str:
    """从 Header 提取 Token"""
    return authorization.split(" ")[1]  # "Bearer xxx" → "xxx"


async def get_current_user(token: str = Depends(get_token)) -> dict:
    """从 Token 解析当前用户"""
    user = decode_jwt(token)
    return user


async def get_db():
    """获取数据库连接"""
    db = Database(...)
    try:
        yield db
    finally:
        await db.close()


# 接口：三个依赖自动串联
@app.get("/me")
async def get_profile(
    user: dict = Depends(get_current_user),  # 依赖 get_token → get_current_user
    db = Depends(get_db),                    # 独立依赖
):
    profile = await db.query("SELECT * FROM profiles WHERE user_id = ?", user["id"])
    return profile

# 调用链: get_token → get_current_user ─┐
#                                       ├→ get_profile(user, db)
#         get_db ────────────────────────┘
```

### 7.3 依赖的组合与复用

```python
# 定义一个通用的"需要权限"依赖
def require_role(role: str):
    """闭包：生成特定角色的校验依赖"""
    async def checker(user = Depends(get_current_user)):
        if user.get("role") != role:
            raise HTTPException(403, f"需要 {role} 权限")
        return user
    return checker


# 使用 — 代码复用，声明即所得
@app.post("/admin/users")
async def create_admin_user(
    user = Depends(require_role("admin")),  # 自动校验 admin 角色
):
    return {"message": f"管理员 {user['name']} 创建了新用户"}


@app.post("/items")
async def create_item(
    user = Depends(require_role("editor")), # 同一个依赖，不同角色
):
    return {"message": f"编辑 {user['name']} 创建了商品"}
```

### 7.4 依赖就是中间件

```python
# 依赖可以测量接口耗时
import time

async def measure_time():
    start = time.time()
    yield                        # ← yield 之前的代码 = 请求前执行
    elapsed = time.time() - start  # ← yield 之后的代码 = 响应后执行
    print(f"接口耗时: {elapsed:.2f}秒")


@app.get("/slow-operation")
async def slow_op(timer = Depends(measure_time)):
    await asyncio.sleep(1)       # 模拟慢操作
    return {"done": True}

# 输出: 接口耗时: 1.00秒
```

---

## 8. 中间件 Middleware

中间件在**每个请求**到达路由前和返回响应后执行：

```python
from fastapi import FastAPI, Request
import time

app = FastAPI()


# 自定义中间件 — 记录每个请求的耗时
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()

    # ① 请求前 — 记录开始时间
    response = await call_next(request)  # ← 调用下一个中间件/路由

    # ② 响应后 — 添加响应头
    process_time = time.time() - start
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

### 中间件 vs 依赖

| | 中间件 | 依赖 Depends |
|------|--------|-------------|
| 作用范围 | **所有**请求 | 声明的接口 |
| 执行时机 | 路由之前/之后 | 路由处理函数内 |
| 典型用途 | 日志、CORS、限流、异常捕获 | 认证、数据库连接、权限校验 |
| 代码复用 | 全局一次性配置 | 按接口声明 |

---

## 9. 应用生命周期 Lifespan

应用启动和关闭时需要做的事：初始化数据库、注册工具、清理连接。

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ═══════════════════════════════════
    # 启动时执行（yield 之前）
    # ═══════════════════════════════════
    await init_database()
    register_all_tools()
    start_background_scheduler()
    print("✅ 应用启动完成")

    yield  # ← 应用运行中...

    # ═══════════════════════════════════
    # 关闭时执行（yield 之后）
    # ═══════════════════════════════════
    await close_database_connections()
    await close_redis()
    print("✅ 应用优雅关闭")


app = FastAPI(lifespan=lifespan)
```

---

## 10. 异常处理

```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI()


# ① 触发 HTTP 异常 — 返回标准错误码
@app.get("/items/{item_id}")
async def get_item(item_id: int):
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="ID 必须大于 0")
    if item_id == 999:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"id": item_id}


# ② 全局异常捕获 — 兜底
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "type": type(exc).__name__,
        },
    )


# ③ 自定义异常 + 专属处理器
class BusinessError(Exception):
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError):
    return JSONResponse(
        status_code=422,
        content={"error": exc.message, "code": exc.code},
    )
```

---

## 11. 后台任务 Background Tasks

有些操作不需要阻塞用户等待：

```python
from fastapi import BackgroundTasks


# 方式 1: FastAPI 内置 BackgroundTasks
@app.post("/send-email")
async def send_email(email: str, background_tasks: BackgroundTasks):
    # 立即返回，邮件在后台发送
    background_tasks.add_task(send_email_async, email)
    return {"message": "邮件将在后台发送"}


async def send_email_async(email: str):
    await asyncio.sleep(5)  # 模拟慢操作
    print(f"邮件已发送到 {email}")
```

```python
# 方式 2: asyncio.create_task — 更灵活的后台任务
import asyncio

@app.post("/index-recipes")
async def trigger_index():
    # 创建后台任务，不等待
    asyncio.create_task(heavy_indexing_job())
    return {"message": "索引任务已在后台启动"}


async def heavy_indexing_job():
    """BGE-M3 索引菜谱到向量库 — 可能需要 30 秒"""
    await asyncio.sleep(5)       # 等模型加载
    await index_recipes_to_db()   # 索引
    print("✅ 索引完成")
```

**两种方式的区别**：

| | BackgroundTasks | asyncio.create_task |
|------|----------------|---------------------|
| 生命周期 | 跟随请求（响应返回后就没了）| 独立于请求 |
| 适用场景 | 发邮件、写日志（耗时 < 5s）| 长时间任务（索引、训练）|
| 错误处理 | 需要自己 try/except | 需要自己 try/except |

---

## 12. 流式响应 StreamingResponse / SSE

### 12.1 普通流式响应

```python
from fastapi.responses import StreamingResponse

@app.get("/download")
async def download_file():
    """大文件下载，不一次性加载到内存"""
    def file_generator():
        with open("large_file.txt", "rb") as f:
            while chunk := f.read(1024 * 1024):  # 每次读 1MB
                yield chunk

    return StreamingResponse(
        file_generator(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=large_file.txt"},
    )
```

### 12.2 SSE（Server-Sent Events）— 打字机效果

这是本项目最核心的前端交互方式。前端一行一行收到 LLM 的输出：

```python
from fastapi.responses import StreamingResponse
import json
import asyncio


@app.get("/chat/stream")
async def chat_stream(prompt: str):
    """LLM 流式对话 — 打字机效果"""

    async def event_generator():
        # 模拟 LLM 逐字输出
        full_response = "根据您冰箱里的食材，推荐以下菜谱：\n1. 蒜蓉菠菜\n2. 番茄炒蛋"
        for char in full_response:
            await asyncio.sleep(0.05)  # 模拟生成延迟
            # SSE 格式: data: {json}\n\n
            yield f"data: {json.dumps({'text': char}, ensure_ascii=False)}\n\n"

        # 发送结束信号
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
```

**前端接收**：

```javascript
const eventSource = new EventSource("/chat/stream?prompt=你好");

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.done) {
        eventSource.close();
    } else {
        chatBox.innerHTML += data.text;  // 逐字追加
    }
};
```

---

## 13. CORS 跨域配置

前端和后端部署在不同端口/域名时，需要配置 CORS：

```python
from fastapi.middleware.cors import CORSMiddleware

# 开发环境 — 允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],             # 允许所有域名
    allow_credentials=True,
    allow_methods=["*"],             # 允许所有 HTTP 方法
    allow_headers=["*"],             # 允许所有请求头
)

# 生产环境 — 限制来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-app.com",      # 只允许你自己的域名
        "https://admin.your-app.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],   # 只允许需要的
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## 14. 静态文件服务

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ① 挂载整个目录 — CSS/JS/图片
app.mount("/static", StaticFiles(directory="frontend"), name="static")
# 现在: /static/style.css → frontend/style.css
#       /static/app.js    → frontend/app.js


# ② 单个文件 — SPA 入口
@app.get("/app")
async def serve_spa():
    return FileResponse("frontend/index.html")


# ③ 网站图标
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("frontend/favicon.png", media_type="image/png")
```

---

## 15. 认证与授权 — JWT

```python
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()
SECRET_KEY = "your-secret-key"


# ① 生成 Token
def create_access_token(user_id: str, name: str) -> str:
    payload = {
        "user_id": user_id,
        "name": name,
        "exp": datetime.utcnow() + timedelta(hours=24),  # 24 小时过期
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


# ② 校验 Token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token 无效")


# ③ 使用
@app.post("/login")
async def login(email: str, password: str):
    # 验证密码...
    token = create_access_token(user_id="u001", name="张三")
    return {"access_token": token, "token_type": "bearer"}


@app.get("/me")
async def get_profile(user = Depends(get_current_user)):
    return {"user_id": user["user_id"], "name": user["name"]}
```

---

## 16. 限流 Rate Limiting

```python
# 使用 slowapi 库
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.get("/limited")
@limiter.limit("5/minute")   # 每分钟最多 5 次
async def limited_endpoint(request: Request):
    return {"message": "这个接口被限流了"}


@app.post("/chat")
@limiter.limit("20/minute")  # 对话接口每分钟 20 次
async def chat(request: Request):
    ...
```

---

## 17. 自动 API 文档 — Swagger / ReDoc

FastAPI **零配置**自动生成交互式 API 文档：

```
启动应用后访问:
  http://localhost:8000/docs    → Swagger UI（可以测试接口！）
  http://localhost:8000/redoc   → ReDoc（更美观的文档）
```

### 自定义文档信息

```python
app = FastAPI(
    title="家务 AI 管家 API",
    version="5.5.0",
    description="基于 ReAct Agent 的智能家庭管理 API",
    docs_url="/docs",        # Swagger 路径（设为 None 可禁用）
    redoc_url="/redoc",      # ReDoc 路径
    openapi_url="/openapi.json",  # OpenAPI JSON 路径
)

# 你的 Pydantic 模型自动变成文档示例：
# - Field(description="...") → 字段说明
# - Field(ge=0, le=100) → 数值范围
# - response_model → 响应示例
```

---

## 18. 异步支持 — async/await 原生

```python
# FastAPI 同时支持同步和异步函数

# 异步（推荐 — 不阻塞事件循环）
@app.get("/async")
async def async_endpoint():
    data = await fetch_from_db()     # await 不阻塞
    result = await call_llm_api()    # 其他请求可以同时处理
    return result


# 同步（FastAPI 会自动放到线程池执行，不阻塞主线程）
@app.get("/sync")
def sync_endpoint():
    time.sleep(2)       # ← FastAPI 自动放到线程池
    return {"done": True}


# 混用
@app.get("/mixed")
async def mixed():
    # 异步操作
    data = await async_fetch()

    # 同步阻塞操作 → 手动放到线程池
    import asyncio
    result = await asyncio.to_thread(time.sleep, 1)

    return data
```

---

## 19. 进阶模式

### 19.1 路由分组 — APIRouter

当项目变大，把所有接口写在 `main.py` 里不可维护：

```python
# routes/users.py
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["用户管理"])

@router.get("/")
async def list_users():
    return [{"id": 1, "name": "张三"}]

@router.post("/")
async def create_user(name: str):
    return {"id": 2, "name": name}
```

```python
# routes/orders.py
from fastapi import APIRouter

router = APIRouter(prefix="/orders", tags=["订单管理"])

@router.get("/")
async def list_orders():
    return [{"id": 101, "status": "shipped"}]
```

```python
# main.py — 统一注册
from fastapi import FastAPI
from routes import users, orders

app = FastAPI()
app.include_router(users.router)
app.include_router(orders.router)
# 实际路径: /users/  /orders/
```

### 19.2 WebSocket 支持

```python
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()  # 接受连接
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"收到: {data}")
    except WebSocketDisconnect:
        print(f"客户端 {client_id} 断开")
```

### 19.3 文件上传

```python
from fastapi import UploadFile, File

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # 读取内容
    content = await file.read()

    # 保存到磁盘
    with open(f"uploads/{file.filename}", "wb") as f:
        f.write(content)

    return {
        "filename": file.filename,
        "size": len(content),
        "content_type": file.content_type,
    }
```

### 19.4 条件请求缓存 — ETag / 304

```python
from fastapi import Request, Response

@app.get("/items/{item_id}")
async def get_item(item_id: int, request: Request, response: Response):
    item = {"id": item_id, "data": "..."}
    etag = f"\"{hash(str(item))}\""

    # 如果客户端缓存的版本没变 → 返回 304
    if request.headers.get("if-none-match") == etag:
        response.status_code = 304
        return response

    response.headers["ETag"] = etag
    return item
```

---

## 20. 更多进阶主题

### 21.1 依赖覆盖 — 测试时替换依赖

```python
from fastapi.testclient import TestClient

app = FastAPI()

async def get_real_db():
    return "Real Database"

@app.get("/data")
async def get_data(db = Depends(get_real_db)):
    return {"db": db}


# 测试时覆盖依赖
def test_get_data():
    # 把真实的数据库依赖替换成假的
    async def override_get_db():
        return "Test Database"

    app.dependency_overrides[get_real_db] = override_get_db

    client = TestClient(app)
    response = client.get("/data")
    assert response.json() == {"db": "Test Database"}

    # 清理
    app.dependency_overrides.clear()
```

### 21.2 测试 — TestClient

```python
from fastapi.testclient import TestClient
import pytest

client = TestClient(app)


def test_root():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    assert "name" in response.json()


def test_create_item():
    """测试 POST"""
    response = client.post("/items/", json={"name": "番茄", "price": 3.5})
    assert response.status_code == 200
    assert response.json()["name"] == "番茄"


def test_validation_error():
    """测试参数校验"""
    response = client.post("/items/", json={"name": "", "price": -1})
    assert response.status_code == 422  # Pydantic 校验失败的默认状态码


def test_async_endpoint():
    """测试异步接口"""
    response = client.get("/async-data")
    assert response.status_code == 200


@pytest.mark.parametrize("item_id,expected", [
    (1, 200),
    (0, 400),
    (-1, 400),
    (999, 404),
])
def test_edge_cases(item_id, expected):
    """参数化测试边界情况"""
    response = client.get(f"/items/{item_id}")
    assert response.status_code == expected
```

### 21.3 Pydantic Settings — 配置管理

```python
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置 — 自动从 .env 文件 / 环境变量读取"""

    # 核心配置
    app_name: str = "My App"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_debug: bool = False

    # LLM 配置
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field(default="deepseek-chat", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.deepseek.com/v1", alias="OPENAI_BASE_URL")

    # 数据库配置
    database_url: str = Field(default="sqlite+aiosqlite:///./data.db", alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")

    # CORS
    cors_allowed_origins: str = "*"

    class Config:
        env_file = ".env"           # 自动读取 .env 文件
        env_file_encoding = "utf-8"
        case_sensitive = False      # 环境变量名不区分大小写


# 使用
settings = Settings()  # 自动从 .env 和环境变量读取
print(settings.app_name)      # → "Agent of Life"
print(settings.app_port)      # → 8000
```

### 21.4 路径操作高级配置

```python
@app.get(
    "/items/{item_id}",
    response_model=ItemResponse,
    status_code=200,
    tags=["商品管理"],           # Swagger 分组
    summary="获取商品详情",       # Swagger 标题
    description="根据商品 ID 返回详细信息，包括价格和库存",
    response_description="成功返回商品信息",
    deprecated=False,            # 标记为已废弃
    responses={
        200: {"description": "成功"},
        404: {"description": "商品不存在"},
        422: {"description": "参数错误"},
    },
)
async def get_item(item_id: int):
    ...
```

### 21.5 Cookie 读写

```python
from fastapi import Cookie, Response


@app.post("/login")
async def login(response: Response, username: str):
    # 设置 Cookie
    response.set_cookie(
        key="session_id",
        value="abc123",
        httponly=True,       # JS 无法访问（防 XSS）
        secure=True,         # 仅 HTTPS
        samesite="lax",      # 跨站策略
        max_age=3600,        # 1 小时过期
    )
    return {"message": "登录成功"}


@app.get("/profile")
async def get_profile(session_id: str = Cookie(None)):
    """从 Cookie 读取 session"""
    if not session_id:
        return {"error": "未登录"}
    return {"session": session_id}


@app.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_id")
    return {"message": "已退出"}
```

### 21.6 Form 表单和文件上传

```python
from fastapi import Form, File, UploadFile


# application/x-www-form-urlencoded
@app.post("/login-form")
async def login_form(
    username: str = Form(...),
    password: str = Form(...),
):
    return {"username": username}


# 同时上传文件 + 表单字段
@app.post("/upload-with-meta")
async def upload_with_meta(
    file: UploadFile = File(...),
    title: str = Form(...),
    tags: str = Form(""),
):
    content = await file.read()
    return {
        "filename": file.filename,
        "size": len(content),
        "title": title,
        "tags": tags.split(","),
    }


# 多文件上传
@app.post("/upload-multiple")
async def upload_multiple(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        content = await file.read()
        results.append({"filename": file.filename, "size": len(content)})
    return {"uploaded": len(results), "files": results}
```

### 21.7 数据库集成 — SQLAlchemy 异步

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


# ① 引擎
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    echo=False,
    pool_size=20,
    max_overflow=10,
)


# ② 会话工厂
async_session = async_sessionmaker(engine, expire_on_commit=False)


# ③ 依赖注入
async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ④ 使用
@app.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).limit(10))
    return result.scalars().all()
```

### 21.8 分页标准模式

```python
from fastapi import Query
from pydantic import BaseModel


class PaginationParams:
    """分页参数 — 可复用的依赖"""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


class PaginatedResponse(BaseModel):
    """分页响应 — 可复用的模型"""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


@app.get("/items", response_model=PaginatedResponse)
async def list_items(
    pagination: PaginationParams = Depends(),
    db = Depends(get_db),
):
    # 查总数
    total = await db.scalar(select(func.count()).select_from(Item))

    # 查当前页
    items = await db.execute(
        select(Item).offset(pagination.offset).limit(pagination.page_size)
    )

    return {
        "items": items.scalars().all(),
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": (total + pagination.page_size - 1) // pagination.page_size,
    }
```

### 21.9 部署 — Gunicorn + Uvicorn Workers

```python
# 单进程（开发用）
# uvicorn main:app --reload

# 多进程（生产用 — 利用多核 CPU）
# gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
#                     ↑ worker数  ↑ ASGI worker
# 一般设为 CPU 核心数 × 2 + 1

# Docker 部署
# Dockerfile:
# CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker",
#      "--bind", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30"]
```

---

## 21. 本项目实战解析

### 20.1 你的项目用了这些特性

```
特性                   在哪                        为什么这样用

APIRouter               api/routes/agent.py         按业务拆分路由（agent, auth, dashboard...）
Depends                 api/deps.py                 依赖注入（crew, memory, profile_mgr）
lifespan                main.py:72                  启动时注册工具、初始化数据库、启动调度器
Pydantic Models         models/schemas.py           40+ 个数据模型，全部自动校验
CORSMiddleware          main.py:159                 前端跨域访问
global_exception_handler  main.py:223               全局异常兜底
StreamingResponse       api/routes/agent.py:90      SSE 流式对话
asyncio.create_task     main.py:99                  后台索引菜谱，不阻塞启动
BackgroundTasks         —                           可用但没用
WebSocket               —                           可用但没用
StaticFiles             main.py:243                 前端文件服务
JWT                    api/routes/auth.py           用户认证
RateLimiting           main.py:18                   慢API 限流
OpenTelemetry          main.py:45                   生产环境链路追踪
```

### 20.2 你的依赖注入是怎么设计的

```python
# api/deps.py — 所有"可注入的资源"都在这里定义

async def get_crew() -> HouseholdCrew:
    """获取 Agent 战队"""
    return get_household_crew()

async def get_memory() -> ConversationMemory:
    """获取对话记忆"""
    return get_conversation_memory()

async def get_profile_mgr() -> UserProfileManager:
    """获取用户画像管理器"""
    return get_profile_manager()
```

```python
# api/routes/agent.py — 接口中声明依赖

@router.post("/chat")
async def chat(
    agent_request: AgentRequest,
    crew: HouseholdCrew = Depends(get_crew),         # ← 注入
    memory: ConversationMemory = Depends(get_memory), # ← 注入
    profile_mgr: UserProfileManager = Depends(get_profile_mgr),  # ← 注入
    user_id: str = Depends(get_current_user),          # ← 注入
):
    # 函数体内直接用，不需要手动创建
    profile = await profile_mgr.get_profile(user_id)
    response = await crew.chat(agent_request)
    await memory.add_message(...)
```

**好处**：
- 测试时可以 mock 依赖（传入假的 memory、假的 crew）
- 依赖的创建逻辑集中管理（`deps.py`），不会散落在 10 个路由文件里
- 接口函数签名清晰表达了"我需要什么"

### 20.3 你的 Lifespan 启动流程

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ──── 启动 ────
    register_all_tools()          # 注册 40+ 工具
    await init_db()               # 创建数据库表
    get_scheduler()               # 启动定时任务
    asyncio.create_task(_index_recipes_bg())  # 后台索引

    yield  # ← 应用运行

    # ──── 关闭 ────
    await memory.close()          # 关闭 Redis 连接
```

---

## FastAPI 常用模式速查

```python
# 路径参数
@app.get("/users/{user_id}")
async def get_user(user_id: int): ...

# 查询参数
@app.get("/search")
async def search(q: str, page: int = 1): ...

# 请求体
@app.post("/users")
async def create(user: UserModel): ...

# 混合
@app.put("/users/{user_id}")
async def update(user_id: int, user: UserModel, token: str = Depends(get_token)): ...

# 依赖注入
async def get_db(): yield db
@app.get("/items")
async def items(db = Depends(get_db)): ...

# 流式响应
return StreamingResponse(generator(), media_type="text/event-stream")

# 文件响应
return FileResponse("path/to/file")

# 后台任务
background_tasks.add_task(send_email, email)

# 异常
raise HTTPException(404, "Not found")

# 全局异常
@app.exception_handler(Exception)
async def handler(request, exc): ...

# 限流
@limiter.limit("5/minute")
```

---

> **FastAPI 的哲学**：写 Python 类型，剩下的编译器帮你搞定。类型注解 = 数据校验 + API 文档 + 编辑器提示，一举三得。
