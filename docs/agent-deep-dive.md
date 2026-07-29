# Agent of Life - Agent 系统深度解析

> 自研 ReAct Agent + Function Calling + 意图路由 + 安全护栏 + 自动修复
> Agent 核心约 1,764 行 | 全文约 13,500 行

---

## 1. 整体架构

四个文件的分工和依赖：

- **HouseholdCrew** (crew.py 81行) -- 对外门面: chat/chat_stream/workflow
- **UnifiedAgent** (unified_agent.py 91行) -- 配置层: system_prompt + 工具清单
- **BaseAgent** (base_agent.py 1375行) -- 核心引擎: ReAct循环 + ToolRegistry
- **IntentRouter** (intent_router.py 217行) -- 意图路由: 规则/缓存/LLM

BaseAgent 是纯引擎，不绑定具体工具。UnifiedAgent 只注入管家 prompt + 工具清单。

---

## 2. 系统启动 (lifespan)

文件: backend/app/main.py:71-109

FastAPI 启动时按顺序执行 5 步：

1. **register_all_tools()** -- 40+ 工具注册到 ToolRegistry
2. **init_db()** -- 连 PostgreSQL，自动建表
3. **get_scheduler()** -- 启动定时调度器
4. **\_index_recipes_bg()** -- 后台: 等5秒后将50道菜谱+8篇知识嵌入 Qdrant
5. **yield** -- 就绪，接受 HTTP 请求

shutdown 时: memory.close() 关闭 Redis 连接。

---

## 3. 工具注册 (register_all_tools)

文件: base_agent.py:1173-1376

每条注册格式: ToolRegistry.register(name, func, desc, params_schema, danger_level)

**40+ 工具来源分布:**

| 来源               | 数量 | 代表工具                                               |
| ------------------ | :--: | ------------------------------------------------------ |
| shopping_tools     |  8   | get_fridge_inventory, add_fridge_item, compare_prices  |
| recipe_tools       |  4   | search_recipes, get_recipe_detail, generate_meal_plan  |
| appliance_tools    |  4   | get_appliance_status, generate_off_peak_schedule       |
| maintenance_tools  |  4   | check_maintenance_due, find_service_contact            |
| security_tools     |  6   | check_door_status, set_away_mode, get_elderly_activity |
| calendar_tools     |  4   | get_weekly_schedule, find_free_time_slots              |
| household_tools    |  3   | track_packages, get_community_notices                  |
| notification_tools |  2   | send_notification, send_bill_reminder                  |
| web_search_tools   |  2   | web_search, search_recipe_videos                       |
| vision_tools       |  1   | analyze_image                                          |
| 内联定义           |  2   | search_knowledge_base, recall_user_memory              |

**danger_level 三级:**

| 级别      | 含义             | 数量 | 例子                                   |
| --------- | ---------------- | :--: | -------------------------------------- |
| safe      | 纯读取           |  35  | get_fridge_inventory, search_recipes   |
| caution   | 写入但不影响安全 |  3   | send_notification                      |
| dangerous | 影响物理世界     |  2   | control_smart_appliance, set_away_mode |

两个内联工具直接在注册函数内定义，是调用底层子系统的桥梁。

---

## 4. 工具实现模式

统一契约: 输入=函数参数 | 输出=dict/list | 异常=返回 error dict

### 模式1: 读数据库 -- get_fridge_inventory

SQLAlchemy 查询 -> 手动转纯 dict 列表 -> 返回。确保 JSON 可序列化。

### 模式2: 写数据库 -- add_fridge_item

参数校验 -> 同名食材累加 -> 否则新增 -> commit。

### 模式3: 纯计算 -- generate_off_peak_schedule

数据源: REAL_APPLIANCES(5台型号) + 北京真实峰谷电价。
算法: 筛选错峰设备 -> 按功率降序 -> 22:00起排时间 -> 算谷电费 -> 对比省多少。

### 模式4: 调子系统

- search_knowledge_base -> RAGChain -> HybridRetriever -> Qdrant 四阶段检索
- recall_user_memory -> ConversationMemory -> Qdrant 语义搜索 -> user_id过滤

---

## 5. 意图路由器 (IntentRouter)

文件: intent_router.py (217行)

**问题:** 40+ 工具 schema 约 8000 tokens，全传浪费且降低准确率。
**方案:** 三层路由缩减到 8-14 个候选。

### 调用位置 (\_prepare_context 中)

intent_label, candidate_tools = await router.route(message)
routed_tools = [t for t in candidate_tools if t in self.tool_names]
if len(routed_tools) < 5: routed_tools = self.tool_names # 兜底

### 第1层: 规则匹配 (0ms, 覆盖80%)

按优先级检查关键词:

1. 寒暄: 你好/hi/在吗 -> general
2. 购物: 冰箱/购物清单/快递 -> shopping
3. 菜谱: 怎么做/菜谱/红烧 -> meal
4. 家电: 空调/洗衣机/错峰 -> appliance
5. 维保: 维修/账单/缴费 -> maintenance
6. 安防: 门窗/监控/布防 -> security
7. 事务: 日程/社区/安排 -> household
8. 综合: 巡检/概览 -> general

### 第2层: 内存缓存 (<1ms)

cache_key = message[:100].lower(), LRU淘汰(超200条删最早30条)

### 第3层: LLM分类 (~500ms)

max_tokens=20, temperature=0。输出验证+模糊匹配兜底。

### 六大领域映射

| 领域        | 工具数 | 通用工具(任何域都带)  |
| ----------- | :----: | --------------------- |
| shopping    |   7    | recall_user_memory    |
| meal        |   6    | search_knowledge_base |
| appliance   |   4    | web_search            |
| maintenance |   5    | analyze_image         |
| security    |   6    |                       |
| household   |   6    |                       |

**效果:** 8000 tokens -> 2000 tokens，每次节省约 6000 input tokens。

---

## 6. 请求准备流水线 (\_prepare_context)

文件: base_agent.py:266-356

run() 和 run_stream() 共享入口，保证两条路径行为一致。六步流水线:

1. 提取已确认工具集合 (安全护栏回传)
2. 意图路由 (40+ -> 8-14 候选)
3. 长期记忆注入 (仅首次对话, \_memory_injected 去重)
4. \_build_full_prompt() 拼接 System Prompt
5. Plan & Execute (含多意图关键词才触发 LLM 拆分)
6. 历史加载 (大于5条: 旧消息 LLM 压缩 + 最近5条原样)

\_build_full_prompt 拼接顺序: 业务Prompt -> 用户档案 -> 用户ID+时间 -> 长期记忆 -> 行为约束 -> 执行计划(可选)

---

## 7. ReAct 循环

### run() 非流式 (base_agent.py:358-636)

核心循环:

```
for iteration in range(10):
  resp = await LLM(messages, tools)  # 3次退避重试
  if resp.tool_calls:
    results = await asyncio.gather(*[call_tool(tc) for tc in tool_calls])
    for each result: 安全检测 + 视频提取 + 自动修复 + 注入 messages
    continue
  else:
    break  # 纯文本 = 最终答案
```

动态置信度 = 0.7 + 工具成功率\*0.25 (范围 0.70-0.95)。
善后: 偏好提取(后台) + 视频卡片 + \_persist_trace 写入数据库。

### run_stream() 流式 (base_agent.py:688-981)

与 run() 五大区别:

| 维度       | run()               | run_stream()              |
| ---------- | ------------------- | ------------------------- |
| LLM调用    | stream=False 一次性 | stream=True 逐chunk       |
| 推理文本   | 直接返回            | 缓冲不yield(避免干扰用户) |
| tool_calls | 完整列表            | 手动拼装id/name/arguments |
| 视频HTML   | 拼入final_text      | contextvars协程安全传递   |
| 记忆持久化 | 路由层负责          | Agent内部自己负责         |

---

## 8. 安全护栏

完整链路 (人在回路):

1. 注册: ToolRegistry.register(..., danger_level=dangerous)
2. \_call_tool 拦截: 返回 {requires_confirmation:true}
3. ReAct 循环中止: run() return / run_stream() yield JSON
4. 路由层不持久化 (确认请求不污染对话历史)
5. 前端弹窗 showConfirmationDialog()
6. 用户确认 -> 二次请求带 confirmed_tools
7. \_prepare_context -> confirmed_set
8. \_call_tool: confirmed_dangerous=True -> 放行执行

关键设计: 确认信息跨请求传递; 防御深度(护栏在 \_call_tool 而非外层)

---

## 9. 自动修复 (\_auto_fix_and_retry)

文件: base_agent.py:1049-1106

流程: 工具返回 error -> LLM分析(工具名+原参数+错误信息) -> 输出修正JSON -> 重试一次
限制: dangerous工具不走自动修复; 重试保守(1次/15s)

---

## 10. 端到端全链路

以用户输入'红烧肉怎么做'为例, 11步:

1. 前端 sendMessage() -> fetch POST /api/v1/agent/chat/stream
2. FastAPI chat_stream(): 认证 + 查档案
3. Crew -> agent.run_stream()
4. \_prepare_context: 意图路由(meal/10工具) + 记忆注入 + SystemPrompt + 历史
5. ReAct第1轮: LLM -> search_recipes + search_recipe_videos -> asyncio.gather并行
6. ReAct第2轮: LLM(含工具结果) -> 纯文本最终回复
7. 善后: 追踪入库 + 视频HTML(contextvars) + 记忆持久化 + 偏好提取
8. SSE回传: data:{content:...} -> data:{video:...} -> data:{done:true}
9. 前端解析: reader -> JSON.parse -> 打字机渲染
10. 渲染完成: Markdown->HTML + 视频卡片 + 操作按钮
11. 用户看到完整回复

---

## 11. 关键文件索引

| 文件                          | 行数 | 核心职责                                 |
| ----------------------------- | :--: | ---------------------------------------- |
| agents/base_agent.py          | 1375 | ReAct循环+ToolRegistry+安全护栏+自动修复 |
| agents/intent_router.py       | 217  | 规则->缓存->LLM 三层意图分类             |
| agents/unified_agent.py       |  91  | System prompt + 工具清单配置             |
| agents/crew.py                |  81  | 对外门面: chat/chat_stream/workflow      |
| rag/retriever.py              | 424  | 四阶段混合检索: Dense+BM25+RRF+Reranker  |
| rag/qa_chain.py               | 336  | RAG问答链: 检索->生成->自省->Fallback    |
| rag/embeddings.py             | 372  | BGE-M3本地部署: 4级降级策略              |
| memory/conversation_memory.py | 464  | Redis双写+LLM摘要固化+偏好提取           |
| memory/vector_store.py        | 206  | Qdrant向量存储                           |
| tools/shopping_tools.py       | 424  | 冰箱库存/购物清单/超市比价               |
| tools/recipe_tools.py         | 1635 | 50+菜谱库+分词搜索+向量化索引            |
| tools/appliance_tools.py      | 323  | 家电状态/错峰计划(真实电价)              |
| api/routes/agent.py           | 480  | Agent对话/流式SSE/追踪/反馈/视觉         |
| api/routes/auth.py            | 286  | JWT登录注册+图形验证码+管理员            |
| models/database.py            | 223  | 10张表: 用户/冰箱/菜谱/追踪/反馈         |
| models/schemas.py             | 409  | Pydantic校验: 请求/响应/业务模型         |
| config.py                     | 163  | 50+配置项                                |
| main.py                       | 255  | FastAPI入口+lifespan启动流水线           |
