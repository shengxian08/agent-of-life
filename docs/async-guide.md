# 🌀 Python 异步编程完全指南 — async/await + asyncio

> 从零理解异步，先讲原理再结合项目实战

---

## 目录

1. [为什么要异步？—— 一个餐馆的故事](#1-为什么要异步一个餐馆的故事)
2. [同步 vs 异步 — 本质区别](#2-同步-vs-异步--本质区别)
3. [事件循环 Event Loop — 异步的心脏](#3-事件循环-event-loop--异步的心脏)
4. [协程 Coroutine — 可暂停的函数](#4-协程-coroutine--可暂停的函数)
5. [await — 让出控制权](#5-await--让出控制权)
6. [Task — 把协程扔进事件循环](#6-task--把协程扔进事件循环)
7. [asyncio.gather() — 真正的并发](#7-asynciogather--真正的并发)
8. [asyncio.create_task() vs await — 并发 vs 串行](#8-asynciocreate_task-vs-await--并发-vs-串行)
9. [异步上下文管理器 — async with](#9-异步上下文管理器--async-with)
10. [常见坑与最佳实践](#10-常见坑与最佳实践)
11. [结合项目代码讲解](#11-结合项目代码讲解)

---

## 1. 为什么要异步？—— 一个餐馆的故事

想象你开了一家餐馆：

### 同步服务员（一个人死等）

```
顾客A点了一份牛排（需要煎 10 分钟）

服务员：                 厨房：
"牛排一份！"    ──────>
                         🔥煎牛排中...（10分钟）
               <──────   "好了！"
"您的牛排！"    


在此期间，服务员**什么也不干，就站在厨房门口干等 10 分钟**。

顾客B、C、D 全部饿死。
```

### 异步服务员（一个人管全场）

```
服务员接到顾客A点单 → 把单子交给厨房 → 立刻去服务顾客B
                                              ↓
顾客B点单 → 交给厨房 → 立刻去服务顾客C
                              ↓
顾客C点单 → 交给厨房 → 回头看顾客A的牛排好了没
                              ↓
牛排好了 → 上菜！→ 继续去接顾客D...

同一个服务员，一个人服务了所有顾客。
```

**这就是异步的核心思想**：当你在等待一个慢操作（网络请求、数据库查询、文件读写）时，**不要干等，去干别的事**。

---

## 2. 同步 vs 异步 — 本质区别

```python
# ====== 同步版本 ======
import time

def fetch_user(user_id):
    """模拟从数据库查用户"""
    time.sleep(1)   # 假装数据库查询需要 1 秒
    return {"id": user_id, "name": "张三"}

def fetch_orders(user_id):
    """模拟查订单"""
    time.sleep(1)
    return ["订单1", "订单2"]

def main():
    t0 = time.time()
    user = fetch_user(1)      # 等 1 秒
    orders = fetch_orders(1)  # 等 1 秒
    print(f"耗时: {time.time() - t0:.1f}秒")  # → 2.0 秒

# 执行流程:
# |──── fetch_user(1秒) ────|──── fetch_orders(1秒) ────|
#                            总共 2 秒，CPU 利用率 ≈ 0%


# ====== 异步版本 ======
import asyncio

async def fetch_user_async(user_id):
    """模拟从数据库查用户"""
    await asyncio.sleep(1)   # 注意：asyncio.sleep，不是 time.sleep
    return {"id": user_id, "name": "张三"}

async def fetch_orders_async(user_id):
    await asyncio.sleep(1)
    return ["订单1", "订单2"]

async def main_async():
    t0 = time.time()
    # 两个任务同时发起！
    user, orders = await asyncio.gather(
        fetch_user_async(1),       # 同时启动
        fetch_orders_async(1),     # 同时启动
    )
    print(f"耗时: {time.time() - t0:.1f}秒")  # → 1.0 秒！

# 执行流程:
# |──── fetch_user(1秒)   ────|
# |──── fetch_orders(1秒) ────|
#              总共 1 秒，两个任务重叠执行
```

**关键差别**：

| | 同步 | 异步 |
|------|------|------|
| 执行方式 | 一个完了才下一个 | 多个同时进行 |
| 等待时 | CPU 空转（阻塞） | CPU 去干别的事（非阻塞） |
| 耗时 | 2 秒（累加） | 1 秒（重叠） |
| 适用场景 | 计算密集型 | **IO 密集型**（网络/数据库/文件） |

---

## 3. 事件循环 Event Loop — 异步的心脏

`asyncio` 的核心是一个叫**事件循环**的东西。它就是一个永不停歇的调度器：

```
┌─────────────── Event Loop（事件循环） ───────────────┐
│                                                      │
│  待办队列:  [Task A, Task B, Task C, Task D, ...]    │
│                                                      │
│  每一步:                                              │
│    1. 从队列取一个 Task                              │
│    2. 执行它，直到遇到 await（它说"我要等一会"）       │
│    3. 把它挂起，去取出下一个 Task                     │
│    4. 等那个 await 的操作完成了，Task 回到队列末尾     │
│    5. 重复...                                        │
│                                                      │
│  伪代码:                                              │
│  while True:                                         │
│      for task in ready_tasks:                        │
│          step = task.send(None)   # 执行一步          │
│          if step.done:                               │
│              collect_result(task)                     │
│          else:                                       │
│              put_back_in_queue(task)                  │
│      check_io_events()            # 看看哪些 IO 好了  │
└──────────────────────────────────────────────────────┘
```

**重点**：事件循环是**单线程**的。同一时刻只有一个 Task 在跑。并发不等于并行。

```
单线程事件循环 ≠ 多线程并行

 线程1 ──────> 任务A ──> 任务B ──> 任务A ──> 任务C ──>  （单线程，快速切换）
 
 vs
 
 线程1 ──────> 任务A ────────────────────────────────>
 线程2 ──────> 任务B ────────────────────────────────>  （多线程，真正同时）
```

**Python 异步 = 协作式多任务**：每个 Task 在 `await` 时**主动**让出控制权，不是被操作系统抢占。

---

## 4. 协程 Coroutine — 可暂停的函数

### 普通函数 vs 协程

```python
# 普通函数：调用就一口气跑完，中间不能暂停
def normal_func():
    print("第1步")
    print("第2步")
    print("第3步")
    return "完成"

result = normal_func()  # result = "完成"


# 协程：可以中途暂停，之后再恢复
async def coroutine_func():
    print("第1步")
    await asyncio.sleep(1)  # ← 暂停！让出控制权，1秒后恢复
    print("第2步")
    await asyncio.sleep(1)  # ← 暂停！
    print("第3步")
    return "完成"

# 调用 async 函数不会执行它，而是返回一个 coroutine 对象！
coro = coroutine_func()
print(type(coro))  # → <class 'coroutine'>
print(coro)         # → <coroutine object coroutine_func at 0x...>

# 必须交给事件循环才能执行：
result = asyncio.run(coroutine_func())  # → "完成"
```

### 三种创建协程的方式

```python
# 方式 1：async def 函数
async def foo():
    return 42

# 方式 2：基于生成器的协程（Python 3.5 之前，已废弃）
# @asyncio.coroutine
# def foo():
#     yield from asyncio.sleep(1)

# 方式 3：原生协程（Python 3.5+，现在标准）
async def foo():
    await asyncio.sleep(1)
```

---

## 5. await — 让出控制权

`await` 是异步编程最重要的关键字。它的意思是：**"我现在要等这个东西，你（事件循环）先去忙别的，弄完了叫我"**。

### await 后面只能跟"可等待对象"（Awaitable）

```python
# ✅ 可以 await 的东西：
await asyncio.sleep(1)       # 协程
await some_coroutine()        # 协程
await some_task               # Task 对象
await some_future             # Future 对象

# ❌ 不能 await 的东西：
await time.sleep(1)           # 普通函数，不是 Awaitable！
await "hello"                 # 字符串不是 Awaitable！
await 42                      # 整数不是 Awaitable！
```

### await 的执行流程

```python
async def fetch_data():
    print("开始请求...")
    response = await http_call()   # ← ① 暂停，让出控制权
    print(f"收到: {response}")      # ← ③ 恢复，继续执行
    return response

# 时间线:
# [开始请求] ──(await 暂停, CPU 去干别的)──> [收到: xxx]
```

### await vs return 的区别

```python
# return：把值返回给调用者，函数结束
# await：把控制权交还给事件循环，函数暂停但没结束

async def example():
    x = await get_x()   # 暂停 → 等 get_x() 完成 → 拿到值 → 继续
    y = await get_y()   # 暂停 → 等 get_y() 完成 → 拿到值 → 继续
    return x + y         # 返回结果，函数结束
```

---

## 6. Task — 把协程扔进事件循环

协程本身是"不动的"。只有包装成 Task 交给事件循环，它才会被调度执行。

```python
async def say_hello():
    await asyncio.sleep(1)
    print("Hello")

# 方式 1：asyncio.run() — 自动创建事件循环并执行
asyncio.run(say_hello())   # 简单场景用这个

# 方式 2：asyncio.create_task() — 手动创建 Task
async def main():
    task = asyncio.create_task(say_hello())  # ← 立即把协程扔进事件循环
    print("Task 已创建，先去干别的...")
    await task  # 等 task 跑完
    print("完成")

asyncio.run(main())
# 输出:
# Task 已创建，先去干别的...
# Hello
# 完成
```

### Task 的生命周期

```
coroutine ──create_task()──> Task ──事件循环调度──> running
                                                      │
                                              await 某个东西
                                                      │
                                                    paused（挂起）
                                                      │
                                              await 的东西完成了
                                                      │
                                                    running（恢复）
                                                      │
                                                     done（完成）
```

---

## 7. asyncio.gather() — 真正的并发

这是你最常用的并发工具。把多个协程打包，"同时"执行，等全部完成后返回结果。

```python
import asyncio

async def fetch_user(id):
    await asyncio.sleep(1)
    return f"用户{id}"

async def fetch_product(id):
    await asyncio.sleep(0.5)
    return f"商品{id}"

async def fetch_order(id):
    await asyncio.sleep(0.8)
    return f"订单{id}"

# 串行：总共 2.3 秒
async def serial():
    u = await fetch_user(1)       # 1.0s
    p = await fetch_product(1)    # 0.5s
    o = await fetch_order(1)      # 0.8s
    return u, p, o

# 并发：总共 1.0 秒（取最长）
async def concurrent():
    u, p, o = await asyncio.gather(
        fetch_user(1),       # 三个同时启动
        fetch_product(1),
        fetch_order(1),
    )
    return u, p, o
```

### gather 的关键特性

```python
# 1. 顺序保持一致 — 返回值顺序 = 参数顺序
results = await asyncio.gather(task_a, task_b, task_c)
# results[0] 对应 task_a，results[1] 对应 task_b，以此类推

# 2. 默认行为：一个出错，其他继续执行，最后一起抛异常
try:
    await asyncio.gather(task_a, will_error, task_c)
except Exception as e:
    pass  # task_c 仍然完成了，但它的结果丢了

# 3. return_exceptions=True — 异常当作正常返回值
results = await asyncio.gather(
    task_a, will_error, task_c,
    return_exceptions=True,   # ← 关键参数
)
# results = [结果A, ValueError("出错了"), 结果C]
# 不会中断，所有 task 都能拿到结果
```

---

## 8. asyncio.create_task() vs await — 并发 vs 串行

这是最容易搞混的地方。看例子：

```python
# ====== 串行执行 ======
async def serial():
    await fetch_data("A")    # 等 A 完成
    await fetch_data("B")    # 再等 B 完成
    await fetch_data("C")    # 再等 C 完成
    # 耗时：T(A) + T(B) + T(C)

# ====== 并发执行（create_task） ======
async def concurrent():
    task_a = asyncio.create_task(fetch_data("A"))  # 立即启动！
    task_b = asyncio.create_task(fetch_data("B"))  # 立即启动！
    task_c = asyncio.create_task(fetch_data("C"))  # 立即启动！
    # 三个已经在同时跑了
    
    result_a = await task_a  # 可能 B 和 C 早就完了，这里只是取结果
    result_b = await task_b
    result_c = await task_c
    # 耗时：max(T(A), T(B), T(C))

# ====== gather 其实是 create_task 的语法糖 ======
async def with_gather():
    results = await asyncio.gather(
        fetch_data("A"),   # gather 内部帮你 create_task 了
        fetch_data("B"),
        fetch_data("C"),
    )
```

### 什么时候用哪种？

| 场景 | 用什么 |
|------|--------|
| 一堆互不依赖的任务，等全部完成 | `asyncio.gather()` |
| 需要一个任务后台跑，不阻塞当前流程 | `asyncio.create_task()` |
| 必须一个接一个执行（后一步依赖前一步结果） | `await` 串行 |
| 多个任务，但需要对每个分别做错误处理 | `create_task()` + 逐个 `await` |

---

## 9. 异步上下文管理器 — async with

数据库连接、HTTP 会话、文件操作等需要"打开-使用-关闭"的资源，用 `async with`：

```python
# 普通版上下文管理器
with open("file.txt") as f:
    data = f.read()
# 自动 close()

# 异步版上下文管理器
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()
# 自动关闭连接
```

### 原理（你不需要写，但了解一下）

```python
# async with obj 等于:
obj = await obj.__aenter__()
try:
    # 你的代码
    ...
finally:
    await obj.__aexit__(exc_type, exc_val, exc_tb)
```

---

## 10. 常见坑与最佳实践

### ❌ 坑 1：在协程里用 `time.sleep()`

```python
async def bad():
    time.sleep(5)  # ❌ 阻塞整个事件循环！所有其他协程都卡住
    return "done"

async def good():
    await asyncio.sleep(5)  # ✅ 非阻塞，事件循环可以去干别的
    return "done"
```

### ❌ 坑 2：忘记 await

```python
async def fetch():
    return "data"

async def main():
    result = fetch()      # ❌ 没有 await！result 是个 coroutine 对象，不是 "data"
    print(result)         # → <coroutine object fetch at 0x...>
    
    result = await fetch() # ✅ 正确
    print(result)          # → "data"
```

### ❌ 坑 3：在非协程里用 await

```python
def normal_func():
    data = await fetch()  # ❌ SyntaxError！await 只能在 async def 里用

async def async_func():
    data = await fetch()  # ✅ 正确
```

### ❌ 坑 4：create_task 后忘记保存引用

```python
async def main():
    # ❌ task 没有被任何变量引用，可能被垃圾回收
    asyncio.create_task(background_job())
    
    # ✅ 保存引用
    task = asyncio.create_task(background_job())
    # 或者 gather
    await asyncio.gather(background_job())
```

### ❌ 坑 5：循环中 create_task 造成"任务泄露"

```python
async def main():
    # ❌ 创建了 1000 个 task 但没有收集
    for i in range(1000):
        asyncio.create_task(do_something(i))
    
    # ✅ 收集起来
    tasks = []
    for i in range(1000):
        tasks.append(asyncio.create_task(do_something(i)))
    await asyncio.gather(*tasks)
```

### ❌ 坑 6：混用同步和异步代码

```python
# ❌ 在协程里调用同步阻塞函数
async def handler():
    result = blocking_db_query()  # 阻塞整个事件循环！
    return result

# ✅ 用 run_in_executor 把阻塞操作移到线程池
async def handler():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, blocking_db_query)
    return result
```

---

## 11. 结合项目代码讲解

### 11.1 核心模式一：并行工具调用 — `asyncio.gather()`

你项目里最漂亮的异步用法在 [base_agent.py:493-498](backend/app/agents/base_agent.py#L493-L498)：

```python
# LLM 说"我需要调 3 个工具" → 三个工具同时执行！
results = await asyncio.gather(
    *[self._call_tool(name, args, user_id,
                      confirmed_dangerous=(name in confirmed_set))
      for _, name, args in tool_tasks],
    return_exceptions=True,
)
```

**这段代码在干什么？**

想象用户说"帮我检查冰箱库存、规划本周菜谱、看看家电维保情况"。LLM 分析后决定同时调 3 个工具，Agent 收到 3 个 tool_calls。

**如果不用异步（串行）**：
```
get_fridge_inventory() ───1秒───>
                          generate_meal_plan() ───2秒───>
                                                 check_maintenance_due() ───0.5秒───>
                                                                                    总共 3.5 秒
```

**用了 `asyncio.gather()`（并发）**：
```
get_fridge_inventory()   ───1秒───>
generate_meal_plan()     ──────2秒──────>
check_maintenance_due()  ──0.5秒──>
                                    总共 2 秒（取最长的那个）→ 快了 43%
```

这就是为什么 README 里说"40+ 工具**并行调用**"——靠的就是这 5 行 `asyncio.gather()`。

**细节解析**：

```python
return_exceptions=True   # ← 关键！
```

什么意思？假设 3 个工具中有一个报错了：
- 不加这个参数 → `gather()` 立刻抛异常，**其他两个工具的结果全丢了**
- 加了之后 → 异常被包装成返回值，**三个工具都能拿到结果**，后面代码自己判断：

```python
for (tc, tool_name, args), result in zip(tool_tasks, results):
    if isinstance(result, Exception):   # ← 手动判断哪个失败了
        result_str = json.dumps({"error": str(result)})
    else:
        result_str = result
```

---

### 11.2 核心模式二：异步生成器 — SSE 流式对话

在 [agent.py:74-97](backend/app/api/routes/agent.py#L74-L97)：

```python
@router.post("/chat/stream")
async def chat_stream(agent_request, crew, ...):
    async def event_generator():              # ① 定义异步生成器
        async for chunk in crew.chat_stream(agent_request):  # ② async for 消费流
            if chunk.startswith('{'):
                data = json.loads(chunk)
                if data.get("requires_confirmation"):
                    yield f"event: confirm\ndata: {chunk}\n\n"   # ③ yield 推送 SSE
                else:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
            else:
                yield f"data: {json.dumps({'text': chunk})}\n\n"

    return StreamingResponse(        # ④ 返回给客户端
        event_generator(),
        media_type="text/event-stream",
    )
```

这里用到了**异步生成器** `async def` + `yield`：

```
普通函数生成器:       def gen():    yield x  ← 配合 for 用
异步生成器:           async def gen(): yield x  ← 配合 async for 用
```

**时间线**（用户发"帮我检查冰箱库存"）：

```
客户端（浏览器）                    服务端
    │                                │
    │  POST /chat/stream              │
    │ ──────────────────────────────> │
    │                                │ agent.run_stream() 启动
    │                                │  → LLM 思考中...
    │                                │  → 调 get_fridge_inventory() (await)
    │                                │  → 工具返回结果
    │                                │  → LLM 生成回复...
    │  data: {"text": "您的冰箱"}      │  ← yield 第一段文字
    │ <────────────────────────────── │
    │  data: {"text": "库存如下："}    │  ← yield 第二段
    │ <────────────────────────────── │
    │  data: {"text": "菠菜..."}      │  ← yield 第三段
    │ <────────────────────────────── │
    │                                │
    │  前端逐字渲染，像 ChatGPT 一样    │
```

**为什么用异步生成器而不是一次性返回？**

```
一次性返回：  用户等 3 秒 → 啪！全部出来   ← 体验差
SSE 流式：    用户等 0.5 秒 → 一个字一个字蹦出来 ← 体验好
```

---

### 11.3 核心模式三：`async for` — 消费 LLM 流式响应

在 [base_agent.py:753-777](backend/app/agents/base_agent.py#L753-L777)：

```python
async for chunk in resp:       # ← async for 迭代 OpenAI 的流式响应
    if chunk.usage:
        stream_usage = chunk.usage
    delta = chunk.choices[0].delta if chunk.choices else None
    if not delta:
        continue
    if delta.content:
        content_chunks.append(delta.content)   # 收集文字片段
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
```

这是 `async for` 的实战：
- OpenAI API 返回的是一个**异步可迭代对象**（AsyncIterable）
- 每个 chunk 是 LLM 生成的一小段文字或工具调用片段
- `async for` 逐个消费这些 chunk，拼成完整回复
- **关键**：消费时不会阻塞事件循环，其他请求可以同时处理

---

### 11.4 核心模式四：后台任务 — `asyncio.create_task()`

在 [main.py:98-99](backend/app/main.py#L98-L99)：

```python
# 应用启动时
asyncio.create_task(_index_recipes_bg())   # ← 扔后台跑，不阻塞启动
logger.info("Recipe indexing triggered (background)")

async def _index_recipes_bg():
    await asyncio.sleep(5)       # 等 BGE-M3 模型加载完（5秒）
    recipe_count = await index_recipes_to_vectordb()   # 索引菜谱到向量库
    logger.success(f"Recipe indexing complete: {recipe_count}")
```

**不用 `await` 而用 `create_task` 的原因**：

```python
# ❌ 如果用 await：
await _index_recipes_bg()
# 应用会卡在这里 5 秒 + 索引时间，才能接受第一个用户请求

# ✅ 用 create_task：
asyncio.create_task(_index_recipes_bg())
# 立即返回，应用开始接受请求，索引在后台默默进行
```

这就是第 8 章讲的 `create_task` vs `await` 的实际场景。

---

### 11.5 核心模式五：异步上下文管理器 — 数据库会话

你项目里数据库查询的标准写法（到处可见）：

```python
async for session in get_db():
    result = await session.execute(
        select(FridgeItem).where(FridgeItem.user_id == user_id)
    )
    return [{"name": r.name, ...} for r in result.scalars()]
```

这里的 `get_db()` 返回的是一个**异步生成器**，内部大概是：

```python
async def get_db():
    async with async_session_maker() as session:   # async with 管理连接
        yield session                              # 用完后自动 close()
```

每次 `async for session in get_db()` 就自动管理了"获取连接 → 执行查询 → 释放连接"整个生命周期，不需要手动 `session.close()`。

---

### 11.6 整体架构的异步调用链

把整个请求流程串起来看：

```
用户发消息 "检查冰箱库存"
        │
        ▼
┌─ FastAPI 路由层 (agent.py) ────────────────────────┐
│ async def chat(request):                            │
│   profile = await profile_mgr.get_profile()  ← ①    │
│   response = await crew.chat(request)        ← ②    │
│   await memory.add_message(...)              ← ③    │
└─────────────────┬───────────────────────────────────┘
                  │ ②
                  ▼
┌─ HouseholdCrew (crew.py) ──────────────────────────┐
│ async def chat(request):                            │
│   return await self.agent.run(request)              │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─ BaseAgent.run() (base_agent.py) ──────────────────┐
│ for iteration in range(max_iterations):             │
│   resp = await client.chat.completions.create()  ← LLM 调用
│   if msg.tool_calls:                                │
│     results = await asyncio.gather(              ← 并行调用工具
│       *[self._call_tool(...) for ...],              │
│     )                                               │
│   else:                                             │
│     return AgentResponse(response=msg.content)      │
└────────────────────────────────────────────────────┘
```

每一个 `await` 都是让出控制权的机会：
- 等 LLM 回复时，事件循环可以处理其他用户的请求
- 等数据库返回时，事件循环可以继续调度
- 三个工具并行执行时，谁先完成谁先返回

**这就是你的 Agent 能同时服务多个用户的密码**——不是多线程，是单线程异步。

---

### 11.7 一个容易忽略的细节

看 [base_agent.py:395-396](backend/app/agents/base_agent.py#L395-L396)：

```python
await asyncio.sleep(0.5 * (retry + 1))   # 退避重试
```

这是 LLM 调用失败后的"退避等待"。为什么用 `asyncio.sleep` 而不是 `time.sleep`？

```python
# ❌ time.sleep → 阻塞整个事件循环
time.sleep(1.5)   # 这 1.5 秒内，所有其他用户的请求全部卡住

# ✅ asyncio.sleep → 只是这个协程暂停
await asyncio.sleep(1.5)  # 事件循环去处理其他请求，1.5 秒后再回来
```

---

## 总结：你项目里的异步使用清单

| 模式 | 在哪 | 为什么这样用 |
|------|------|-------------|
| `asyncio.gather()` | base_agent.py:493 | 3 个工具同时查 → 快 40%+ |
| `async for` | base_agent.py:753 | 逐片消费 LLM 流式响应 |
| `async def` + `yield` | agent.py:90 + base_agent.py:688 | SSE 推流给前端逐字渲染 |
| `asyncio.create_task()` | main.py:99 | 后台索引菜谱，不阻塞启动 |
| `async for session in get_db()` | 所有工具函数 | 自动管理数据库连接生命周期 |
| `await asyncio.sleep()` | base_agent.py:395 | 退避重试时不让整个服务卡住 |
| `return_exceptions=True` | base_agent.py:497 | 一个工具挂了不影响其他工具的结果 |

> **一句话**：你的 Agent 是一个单线程程序，但因为到处用了 `await`，它看起来像同时在干很多件事——等 LLM 响应时不闲着，去处理别的用户；调 3 个工具时不排队，全都同时发起。

---

---

## 番外：@classmethod 与 cls — 彻底搞懂

> 这节是独立知识点，跟异步无关。后续讲项目的 `ToolRegistry` 时会用到这里的基础。

### 写法长什么样？

```python
class MyClass:
    @classmethod
    def my_method(cls, arg1, arg2):
        # cls 就是 MyClass 这个类本身
        pass
```

两个关键点：
- `@classmethod` — 装饰器，改变方法的调用方式
- `cls` — 第一个参数，**自动**接收类本身（就像 `self` 自动接收实例）

---

### 先回顾：三种方法类型

```python
class Dog:
    species = "犬科"     # 类属性，所有实例共享

    def __init__(self, name):
        self.name = name  # 实例属性，每只狗不同

    # ① 实例方法 — 默认的，最常用的
    def bark(self):                # self = 具体的某只狗
        print(f"{self.name} 汪汪叫")

    # ② 类方法 — 加了 @classmethod
    @classmethod
    def get_species(cls):          # cls = Dog 这个类
        return cls.species

    # ③ 静态方法 — 加了 @staticmethod
    @staticmethod
    def is_dog(animal):
        return animal == "狗"


# 使用对比：
d = Dog("旺财")

d.bark()                # self 自动 = d（旺财这条狗）
Dog.get_species()       # cls 自动 = Dog（整个狗类）
Dog.is_dog("猫")        # 没有 self 也没有 cls，相当于普通函数
```

---

### 三种方法到底差在哪？

| | 实例方法 | 类方法 | 静态方法 |
|------|---------|--------|---------|
| 装饰器 | 无（默认） | `@classmethod` | `@staticmethod` |
| 第一个参数 | `self` → 实例 | `cls` → 类 | 无 |
| 能访问实例属性吗？ | ✅ `self.name` | ❌ 没有 `self` | ❌ |
| 能访问类属性吗？ | ✅ `self.__class__.species` | ✅ `cls.species` | ❌（除非硬编码类名） |
| 能用实例调用吗？ | ✅ | ✅ `d.get_species()` | ✅ `d.is_dog()` |
| 能用类调用吗？ | ❌ `Dog.bark()` 报错 | ✅ `Dog.get_species()` | ✅ `Dog.is_dog()` |
| 典型用途 | 操作具体对象 | 工厂方法 / 单例 / 操作类变量 | 工具函数 |

---

### `cls` 到底是什么？

**`cls` 不是关键字，是一个命名惯例**，就像 `self` 一样。

```python
class Pizza:
    default_size = "中号"     # 类属性

    @classmethod
    def create_large(cls):     # ← cls 就是 Pizza
        cls.default_size = "大号"   # 通过 cls 修改类属性
        return cls()            # 通过 cls 创建实例


# Python 调用时自动做的事情：
Pizza.create_large()
#  ↓ Python 自动变成 ↓
Pizza.create_large(Pizza)
#                   ↑ 这就是 cls 的来源

# 如果用实例调用：
p = Pizza()
p.create_large()
#  ↓ Python 自动变成 ↓
Pizza.create_large(Pizza)
#                   ↑ 不是 p！是用 type(p) 取出了类！
```

**核心规则**：不管你怎么调用（`类.方法()` 还是 `实例.方法()`），`cls` 永远是**这个实例所属的类**。

---

### 继承时 `cls` 的妙用

这是 `@classmethod` 最强大的特性：

```python
class Animal:
    @classmethod
    def create(cls, name):
        return cls(name)    # ← cls 是谁，就创建谁

    def __init__(self, name):
        self.name = name

class Dog(Animal):
    def speak(self):
        return f"{self.name}: 汪汪"

class Cat(Animal):
    def speak(self):
        return f"{self.name}: 喵喵"


# 关键：用子类调用时，cls 就是子类！
dog = Dog.create("旺财")   # cls = Dog, 创建的是 Dog 实例
cat = Cat.create("咪咪")   # cls = Cat, 创建的是 Cat 实例

print(type(dog))   # → <class 'Dog'>
print(dog.speak()) # → "旺财: 汪汪"
print(cat.speak()) # → "咪咪: 喵喵"
```

**如果不用 `@classmethod` 而是硬编码类名**：

```python
class Animal:
    def create(name):          # 没有 cls
        return Animal(name)    # ❌ 硬编码！子类调用也返回 Animal

Dog.create("旺财")   # → Animal 实例，不是 Dog！speak() 方法丢了
```

---

### 什么时候用 `@classmethod`？

#### 场景 1：工厂方法 / 替代构造函数

```python
class User:
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

    @classmethod
    def from_json(cls, json_str):
        """从 JSON 字符串构建 User — 另一种创建方式"""
        import json
        data = json.loads(json_str)
        return cls(id=data["id"], name=data["name"], email=data["email"])

    @classmethod
    def from_database_row(cls, row):
        """从数据库行构建 User"""
        return cls(id=row[0], name=row[1], email=row[2])

# 使用：
user1 = User(1, "张三", "zhang@test.com")               # 正常构造
user2 = User.from_json('{"id": 2, "name": "李四", ...}') # 从 JSON 构造
user3 = User.from_database_row((3, "王五", "wang@test.com")) # 从 DB 构造
```

#### 场景 2：单例模式

```python
class Config:
    _instance = None

    @classmethod
    def get_instance(cls):
        """全局唯一的 Config 实例"""
        if cls._instance is None:
            cls._instance = cls()    # cls 就是 Config
        return cls._instance
```

#### 场景 3：操作类级别的共享状态

你项目里的 `ToolRegistry` 整个就是基于这个模式（后面讲）。

---

### 常见误区

#### ❌ 误区 1：觉得 cls 是关键字

```python
# 以下写法完全等价，但千万别这么干（违反 Python 惯例）：
@classmethod
def method(klass):      # 能跑，但别人会骂你
    return klass.name

@classmethod
def method(this_class): # 能跑，但还是 cls 最标准
    return this_class.name

@classmethod
def method(cls):        # ✅ 标准写法
    return cls.name
```

#### ❌ 误区 2：在类方法里用 `self`

```python
class Foo:
    @classmethod
    def bad(cls, self):   # ❌ self 只是一个普通参数名，不是实例
        print(self.name)

    @classmethod
    def good(cls):        # ✅ cls 是类，只能访问类属性
        print(cls.class_attr)
```

#### ❌ 误区 3：该用 @classmethod 的时候用了 @staticmethod

```python
class Person:
    species = "人类"

    @staticmethod
    def get_species():
        return Person.species   # ❌ 硬编码了 Person

    @classmethod
    def get_species(cls):
        return cls.species      # ✅ 用 cls，子类继承也能正常工作
```

#### ❌ 误区 4：别忘了 first argument 是自动传的

```python
class Test:
    @classmethod
    def method(cls, x):
        return cls.__name__, x

# ✅ 正确 — Python 自动传 cls
Test.method(42)         # → ('Test', 42)

# ❌ 错误 — 手动又传了一个类
Test.method(Test, 42)   # → (Test, Test)，cls 收到的是 Test，x 收到的是 Test！
                        # 但这个方法只有一个额外参数 x... 会报错
```

---

### 与项目代码的关系

你项目里 `ToolRegistry` 是 `@classmethod` 的典型案例——它根本不需要实例化，整个类就是全局单例：

```python
class ToolRegistry:
    _tools: dict = {}           # 类属性，唯一的工具字典

    @classmethod
    def register(cls, name, func, ...):   # cls = ToolRegistry
        cls._tools[name] = {...}          # 操作类级别的 _tools

    @classmethod
    def get(cls, name):                   # cls = ToolRegistry
        return cls._tools.get(name)

# 使用：永远不需要 ToolRegistry()
ToolRegistry.register("search", ...)   # 直接用类调用
ToolRegistry.get("search")             # 直接用类调用
```

为什么不用实例方法？（等讲到项目时展开）

| 概念 | 一句话 | 关键字 |
|------|--------|--------|
| 协程 (coroutine) | 可以暂停和恢复的函数 | `async def` |
| await | "我要等，你先忙别的" | `await xxx` |
| 事件循环 (event loop) | 调度所有协程的管家 | `asyncio.run()` |
| Task | 被扔进事件循环执行的协程 | `asyncio.create_task()` |
| gather | 同时跑多个，全完成后再继续 | `asyncio.gather()` |
| 并发 | 多个任务交替执行（单线程快速切换） | concurrent |
| 并行 | 多个任务同时执行（多核 CPU） | parallel |
| Awaitable | 能被 await 的对象 | coroutine, Task, Future |
| 异步上下文管理器 | 异步版的 `with` | `async with` |
| 异步迭代器 | 异步版的 `for` | `async for` |

---

> **记住一句话**：异步的本质不是"跑得更快"，而是**"等待时不闲着"**。就像你不会站在微波炉前面盯着它转 3 分钟——你会趁这时间切菜、擦桌子、回微信。
