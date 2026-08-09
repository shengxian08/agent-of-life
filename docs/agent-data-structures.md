# AI Agent 数据结构深度知识库

> **覆盖范围**：Agent of Life v5.5 全栈数据模型 + 业界前沿 Agent 架构数据结构
> **编写视角**：从 ReAct Agent 到 Multi-Agent 到 AGI，从消息总线到知识图谱，从状态机到认知架构
> **技术栈**：LangChain / CrewAI / AutoGen / OpenAI Agents SDK / Anthropic MCP / LlamaIndex / LangGraph

---

## 目录

1. [Agent 请求/响应协议与消息模型](#1-agent-请求响应协议与消息模型)
2. [工具系统与 Function Calling 数据结构](#2-工具系统与-function-calling-数据结构)
3. [记忆系统数据结构（短期/长期/工作）](#3-记忆系统数据结构短期长期工作)
4. [ReAct 循环与状态机](#4-react-循环与状态机)
5. [意图路由与调度结构](#5-意图路由与调度结构)
6. [RAG 检索增强生成数据结构](#6-rag-检索增强生成数据结构)
7. [向量存储与 Embedding 抽象](#7-向量存储与-embedding-抽象)
8. [Multi-Agent 编排与通信协议](#8-multi-agent-编排与通信协议)
9. [Agent 安全护栏与确认机制](#9-agent-安全护栏与确认机制)
10. [追踪、可观测性与 Token 审计](#10-追踪可观测性与-token-审计)
11. [Plan-and-Execute 与层次化规划](#11-plan-and-execute-与层次化规划)
12. [业界前沿：Agent 协议与标准](#12-业界前沿agent-协议与标准)
13. [数据结构选型决策框架](#13-数据结构选型决策框架)

---

## 1. Agent 请求/响应协议与消息模型

### 1.1 核心设计原则

Agent 的通信协议是它和外部世界对话的"语言边界"。一个设计良好的 Agent 协议必须满足：

- **幂等性与重放安全**：相同 `session_id` + `message` 的请求应当产生一致结果
- **流式与非流式统一**：`run()` 返回完整响应，`run_stream()` 通过 `AsyncGenerator` 逐步推送
- **安全护栏嵌入协议层**：`confirmed_tools` / `requires_confirmation` 不依赖 Agent 内部状态
- **上下文穿透**：用户画像、长期记忆、历史窗口通过 `context` 字典注入

### 1.2 AgentRequest —— 请求协议

```python
class AgentRequest(BaseModel):
    """业界通用 Agent 请求模型 —— 兼容 OpenAI Agents SDK / LangChain / AutoGen"""
    # -- 会话标识 --
    session_id: str            # UUID，跨轮对话关联
    user_id: str               # 多租户隔离键

    # -- 消息载荷 --
    message: str               # 用户原始输入（纯文本，未来可扩展为 MultimodalPart[]）

    # -- 意图标签 --
    intent: Optional[str]      # 系统路由用，也可由 LLM 自动推断
    # 合法值: shopping / meal / appliance / maintenance / security / household / general

    # -- 上下文注入 --
    context: dict[str, Any]    # 自由态键值对:
    #   profile: UserProfile       → 用户画像
    #   history: ConversationMessage[] → 历史窗口
    #   plan_steps: str[]          → Plan-and-Execute 子任务

    # -- 安全护栏 --
    confirmed_tools: list[dict[str, Any]]  # 用户已确认的危险调用
    # 格式: [{"tool": "set_away_mode", "args": {...}, "confirmed_at": "ISO8601"}]

    # -- 流式开关 --
    stream: bool = False       # True → run_stream()，False → run()
```

### 1.3 AgentResponse —— 响应协议

```python
class AgentResponse(BaseModel):
    session_id: str
    response: str                             # 最终用户可见文本
    intent: str                               # 实际执行的意图域
    tool_calls: list[dict[str, Any]]          # 执行过程中调用的工具记录
    # [{tool, args, result_summary, is_error}]

    data: dict[str, Any]                      # 结构化附加数据
    # e.g. {"videos": [...], "meal_plan": MealPlan.model_dump()}

    suggestions: list[str]                    # 建议下一步操作
    confidence: float                         # 0.0~1.0，AI 对本次回复的置信度估算
    timestamp: datetime

    # ====== 安全护栏协议（关键） ======
    requires_confirmation: bool               # True → 本次回复是"确认申请"而非最终答案
    pending_dangerous_calls: list[dict]       # 挂着待确认的危险调用详情
```

**安全确认流程**：前端看到 `requires_confirmation=True` 时 → (1) 不将 response 视为最终答案 (2) 展示确认弹窗 (3) 用户确认后，带着 `confirmed_tools` 重新发送请求。

### 1.4 业界对比 —— 请求/响应协议

| 框架 | 请求结构 | 特点 |
|------|----------|------|
| OpenAI Agents SDK | `Runner.run(agent, input, context={})` | `context` 是自由态 dict，设计理念一致 |
| LangChain | `AgentExecutor.invoke({"input": ..., "chat_history": ...})` | 字典风格，类型安全性弱于 Pydantic |
| Anthropic MCP | JSON-RPC 2.0 `{"method": "tools/call", ...}` | 标准 RPC 协议，工具调用统一 |
| AutoGen | `ConversableAgent.generate_reply(messages=...)` | 以消息历史为驱动，天然多轮 |
| **Agent of Life** | `agent.run(AgentRequest) → AgentResponse` | Pydantic 类型安全 + 安全护栏原生集成 |

### 1.5 ConversationMessage —— 对话原子

```python
class ConversationMessage(BaseModel):
    """OpenAI Chat Completions API 兼容的消息原子"""
    role: str             # "user" | "assistant" | "system" | "tool"
    content: str          # 文本载荷
    timestamp: datetime
    metadata: dict[str, Any]  # 扩展:
    #   tool_calls: OpenAI 原生 tool_calls 数组
    #   reasoning_content: DeepSeek-R1 思维链
    #   token_count: {prompt, completion}
```

### 1.6 业界前沿 —— Multimodal Message

业界前沿的 Agent 消息不再只有文本，而是 `ContentPart[]` 数组（GPT-4o / Claude 3.5 原生支持）：

```python
class ContentPart(BaseModel):
    type: Literal["text", "image_url", "tool_use", "tool_result"]
    text: Optional[str]
    image_url: Optional[ImageUrl]           # base64 或 URL
    tool_use: Optional[ToolUseBlock]        # Claude 原生工具调用
    tool_result: Optional[ToolResultBlock]  # Claude 原生工具结果
```

你的系统已在 `VisionTools.analyze_image` 中支持图片输入，但消息层仍是纯文本。升级多模态消息协议后可直接对接 GPT-4o / Claude 原生 vision API。

---

## 2. 工具系统与 Function Calling 数据结构

### 2.1 ToolRegistry —— 全局工具注册表

```python
ToolRegistry.register("check_door_status", check_door_status,
    "检查全部门锁状态（入户门/阳台门/车库门）",   # ← 关键：告诉 LLM 这个工具做什么
    {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
        "required": ["user_id"]
    },
    danger_level="safe"                          # ← 安全分级
)
```

**三级安全分级 (danger_level)**：

| level | 含义 | 示例 | LLM 可自由调用? |
|-------|------|------|:---:|
| `safe` | 纯读取/无副作用 | `get_fridge_inventory` | ✅ |
| `caution` | 有副作用但无物理风险 | `send_notification`, `send_bill_reminder` | ✅ |
| `dangerous` | 影响物理世界/安全 | `set_away_mode`, `control_smart_appliance` | ❌ 必须用户确认 |

### 2.2 业界前沿 —— Anthropic MCP (Model Context Protocol)

MCP 把工具定义标准化为 JSON-RPC 协议，不只是函数调用，而是把**资源（Resources）**和**提示词模板（Prompts）**也作为可发现的服务暴露给模型：

```json
{
  "method": "tools/list",
  "result": {
    "tools": [{
      "name": "get_fridge_inventory",
      "description": "查看冰箱食材库存",
      "inputSchema": {
        "type": "object",
        "properties": {"user_id": {"type": "string"}},
        "required": ["user_id"]
      },
      "annotations": {"readOnlyHint": true, "destructiveHint": false}
    }]
  }
}
```

你的 `danger_level` 三级分类比 MCP 的二进制标记更细粒度，但 MCP 的标准化程度更高，更适合多 Agent 间的工具共享。

### 2.3 Function Calling 数据格式（OpenAI 标准）

传给 LLM 的工具定义：

```python
{
    "type": "function",
    "function": {
        "name": "check_door_status",
        "description": "检查全部门锁状态",
        "parameters": {"type": "object", "properties": {...}, "required": [...]}
    }
}
```

LLM 返回的工具调用消息：

```python
{
    "role": "assistant",
    "content": "让我检查一下门锁状态",          # 思考文本（可能为空）
    "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "check_door_status",
            "arguments": '{"user_id": "user_001"}'  # JSON 字符串！
        }
    }],
    "reasoning_content": "..."                # DeepSeek-R1 思维链（可选）
}
```

**⚠️ DeepSeek 特有问题**：如果 LLM 返回了 `reasoning_content`，下一轮构建消息时必须原样附带，否则 DeepSeek API 返回 400。

### 2.4 并行工具调用与自动修复

```python
# 并行执行（关键性能优化 —— 将 N 轮串行压缩为 1 轮）
results = await asyncio.gather(
    *[self._call_tool(name, args, user_id) for _, name, args in tool_tasks],
    return_exceptions=True,  # 单个失败不影响其他
)

# 自动修复：工具返回错误 → LLM 分析 → 生成修复参数 → 重试一次
async def _auto_fix_and_retry(tool_name, args, error_msg, user_id):
    """常见可修复错误：ID 不存在、参数类型错误、缺少必需参数"""
```

### 2.5 工具调用结果序列化（三层递归）

```python
def _serialize_tool_result(obj: Any) -> Any:
    # Layer 1: Pydantic 模型 → dict
    # Layer 2: list/dict 中包含 Pydantic → 递归展开
    # Layer 3: datetime → ISO 字符串
```

---

## 3. 记忆系统数据结构（短期/长期/工作）

### 3.1 三层记忆架构

业界最前沿的 Agent 记忆系统都遵循三层模型（Working → Short-term → Long-term）：

```
┌─────────────────────────────────────────────┐
│         L3: 长期记忆 (Long-term Memory)      │
│   BGE-M3 向量化 → Qdrant 语义检索           │
│   TTL: 90天，固化策略，偏好提取              │
│   「用户喜欢川菜」「上次修空调是 3 月」      │
├─────────────────────────────────────────────┤
│         L2: 短期记忆 (Short-term Memory)     │
│   Redis List + 内存热缓存 (LRU)             │
│   TTL: 7天，滑动窗口 40 条                   │
│   「刚才问了冰箱库存，现在要规划菜谱」        │
├─────────────────────────────────────────────┤
│         L1: 工作记忆 (Working Memory)        │
│   LLM Context Window (messages 列表)         │
│   TTL: 单次请求，Token Budget: 12000          │
│   「当前正在执行的 ReAct 循环上下文」         │
└─────────────────────────────────────────────┘
```

### 3.2 MemoryEntry —— 长期记忆单元

```python
class MemoryEntry(BaseModel):
    """长期记忆的最小单元 —— 存储在向量数据库中"""
    memory_id: str
    user_id: str
    content: str                # 摘要文本 "用户偏好川菜，微辣，不喜欢大蒜"
    memory_type: str            # preference | event | fact | conversation
    embedding: Optional[list[float]]  # BGE-M3 1024维向量
    importance: float           # 0.0~1.0，记忆重要性
    created_at: datetime
    last_accessed: datetime
    access_count: int           # 访问频率，用于记忆衰减决策
```

### 3.3 业界前沿 —— MemGPT / Letta 的记忆模型

MemGPT 把记忆当作操作系统分页管理 —— 核心概念是 **Memory Bank** + **Memory Page**：

```python
class MemoryBank:
    core_memory: CoreMemory      # 永远在 context window 中的核心块
    archival_memory: VectorDB    # 大量向量化的长期记忆
    recall_memory: Deque[Message] # 固定窗口的近期对话

class CoreMemory:
    persona: str                 # Agent 身份描述
    human: str                   # 用户描述/偏好
```

**对比你的系统**：

| 特性 | Agent of Life | MemGPT/Letta |
|------|:---:|:---:|
| 核心记忆注入 | `_build_full_prompt()` 中 profile + memory_context | `CoreMemory` 块始终在 system prompt |
| 长期记忆存储 | Qdrant + BGE-M3 | 同样向量存储 |
| 记忆淘汰策略 | TTL 90天 | 重要性评分 + LRU |
| 记忆固化触发 | 每 6 条消息触发 `_consolidate_if_needed` | 异步后台任务 |
| 偏好自动学习 | `_extract_preferences_bg` 从对话中提取 | `extract_persona()` 类似机制 |

### 3.4 ConversationMemory —— 短期记忆管理（双层存储）

```python
class ConversationMemory:
    """Redis 双向持久化 + 内存热缓存"""

    # 内存层（热缓存，纳秒级读取）
    _memory: dict[str, list[ConversationMessage]]  # {session_id: [...]}

    # 持久层（Redis，重启不丢失）
    # key: "conv:{session_id}"  →  Redis List  →  TTL: 7 天

    # 会话到用户的映射
    _session_users: dict[str, str]  # {session_id: user_id}

    # 语义缓存（防抖，5 分钟 TTL，最大 500 条）
    _semantic_cache: dict[str, tuple[str, datetime]]
```

### 3.5 记忆固化流水线

```
对话进行中 → add_message() 双写内存+Redis
    ↓
数量 ≥ 6 条（memory_consolidation_threshold）
    ↓                       ← asyncio.create_task 后台执行，不阻塞用户
LLM 摘要生成（偏好/重要事实/待办事项 结构化提取）
    ↓
BGE-M3 向量化（1024维）
    ↓
Qdrant upsert（metadata: user_id, session_id, type, timestamp, ttl_days）
    ↓
_summary_cache 记录最后固化时间（防重复，5 分钟冷却）
```

### 3.6 recall_user_memory —— 记忆检索入口

```python
async def recall_user_memory(user_id: str, query: str, top_k: int):
    """检索用户跨会话的长期记忆

    与 search_knowledge_base 的区别:
    - search_knowledge_base → 结构化文档（菜谱知识、维保记录）
    - recall_user_memory    → 对话摘要（偏好习惯、待办事项）
    """
    return {"found": n, "memories": [{"text": ..., "score": ...}, ...]}
```

### 3.7 偏好自动学习

```python
async def extract_and_update_preferences(user_id, dialog_text):
    """从对话中自动提取偏好变化并写回用户画像
    LLM 分析 → 检测新增口味偏好/过敏物/忌口/预算变化
    → 自动调用 UserProfileManager 更新
    防抖: 同一用户 10 分钟内不重复提取"""
```

### 3.8 业界前沿 —— Google DeepMind 的 Infini-Attention

2024 年提出的 Infini-Attention 将记忆压缩与 Attention 机制融合 —— 不是"先检索再注入"，而是记忆直接参与 attention 计算：

```
Q × (K_compressed @ V_compressed)  ← 长期记忆参与 attention
  +
Q × (K_local @ V_local)            ← 短期上下文参与 attention
```

这比"注入 system prompt"更优雅，但需要模型架构级别支持，目前仅限 Google 自家模型。

---

## 4. ReAct 循环与状态机

### 4.1 完整循环结构

```
┌───────────────────────────────────┐
│     _prepare_context()            │
│   意图路由→选择工具子集            │
│   记忆注入→构建 system prompt     │
│   Plan-and-Execute→分解任务        │
│   加载历史→滑动窗口+摘要           │
└───────────────┬───────────────────┘
                ↓
   ┌───────────────────────────────────────────────────┐
   │              ReAct Loop（动态轮次）                │
   │                                                   │
   │  iteration = 0                                    │
   │     ↓                                             │
   │  ┌─────────────────────────────────┐              │
   │  │ 1. LLM Call（stream/non-stream）│              │
   │  │    - 3次退避重试                 │              │
   │  │    - Token 累加                  │              │
   │  └──────────────┬──────────────────┘              │
   │                 ↓                                  │
   │        ┌────────┴────────┐                        │
   │        │                 │                        │
   │   没有tool_calls    有tool_calls                    │
   │        │                 │                        │
   │        ↓                 ↓                        │
   │   ┌─────────┐    ┌─────────────────┐              │
   │   │最终回复 │    │ 防线1: Token预算 │              │
   │   │break    │    │ total > 12000?   │              │
   │   └─────────┘    └────────┬────────┘              │
   │                           ↓                        │
   │                    ┌─────────────────┐              │
   │                    │ 防线2: 死循环检测 │              │
   │                    │ 相同调用 ≥3 次?   │              │
   │                    └────────┬────────┘              │
   │                             ↓                      │
   │                    ┌─────────────────┐              │
   │                    │ 并行执行所有工具  │              │
   │                    │ asyncio.gather   │              │
   │                    └────────┬────────┘              │
   │                             ↓                      │
   │                    ┌─────────────────┐              │
   │                    │ 自动修复（可选） │              │
   │                    └────────┬────────┘              │
   │                             ↓                      │
   │                    ┌─────────────────┐              │
   │                    │ 构建tool消息     │              │
   │                    │ iteration++      │              │
   │                    └────────┬────────┘              │
   │                             │                      │
   │                    （继续循环）←────────────────────┘
   │
   ↓
┌──────────────────────────────────────────┐
│ 后处理: 置信度计算 | 视频卡片 | 偏好提取 │
│        追踪持久化 | 对话历史持久化        │
└──────────────────────────────────────────┘
```

### 4.2 TraceStep —— 每步可观测性

```python
trace_steps: list[dict] = [
    {
        "iteration": 0,
        "step_type": "llm_call",          # llm_call / tool_result / final / error
        "detail": {
            "thought": "让我检查冰箱库存和今天的菜谱推荐",
            "tool_calls_planned": [           # LLM 计划调用哪些工具
                {"name": "get_fridge_inventory", "args": '{"user_id": "u1"}'},
                {"name": "search_recipes", "args": '{"query": "川菜"}'},
            ],
            "tokens": {"prompt": 1234, "completion": 56},
        },
        "duration_ms": 1500,
    },
    {
        "iteration": 0,
        "step_type": "tool_result",
        "detail": {
            "tool": "get_fridge_inventory",
            "args": {"user_id": "u1"},
            "result_summary": '{"items": [{"name": "鸡蛋", "quantity": 6}]}',
            "is_error": False,
        },
        "duration_ms": 0,
    },
]
```

### 4.3 动态轮次策略

```python
plan_count = ctx.get("plan_steps_count", 0)
if plan_count > 1:
    effective_max = min(plan_count * 3 + 2, self.max_iterations)
    # 有 3 步计划 → 最多 11 轮（但不超过配置上限 10）
else:
    effective_max = 5  # 没有计划的简单对话 → 5 轮够了
```

### 4.4 死循环检测

```python
# 签名机制：将本轮的工具调用组合成字符串指纹
this_sig = "|".join(sorted(
    f"{tc.function.name}:{tc.function.arguments[:120]}"
    for tc in msg.tool_calls
))

# 连续两轮相同 → 死循环
if this_sig == last_tool_sig:
    repeat_count += 1
    if repeat_count >= MAX_REPEAT:  # 2 次重复
        break  # 终止循环，返回友好提示
```

**业界对比**：CrewAI 在 `Task` 层面提供 `guardrail` 函数做类似保护。两者可组合使用形成双重保护。

---

## 5. 意图路由与调度结构

### 5.1 分层路由器

```
用户消息
    ↓
┌─────────────────────────────────────────────┐
│ Layer 1: 规则引擎（0ms，覆盖 80%）           │
│   "冰箱里有什么" → shopping                   │
│   "清洗空调" → maintenance                   │
│   "今天吃什么" → meal                         │
│   关键词匹配 + 排除逻辑                        │
├─────────────────────────────────────────────┤
│ Layer 2: 语义缓存（0ms，覆盖 10%）            │
│   _intent_cache: dict[str, str]（最大 200 条）│
│   相同问题 → 直接返回缓存意图                   │
├─────────────────────────────────────────────┤
│ Layer 3: LLM 分类（<500ms，覆盖 10%）         │
│   max_tokens=20，temperature=0               │
│   轻量级，只输出一个标签                       │
└─────────────────────────────────────────────┘
    ↓
根据意图选择工具子集:
  shopping → 7个购物工具    meal → 6个膳食工具
  general  → 全部 40+ 个工具
    +
  COMMON_TOOLS（始终附带）:
    recall_user_memory, search_knowledge_base, web_search, analyze_image
```

### 5.2 领域→工具映射

```python
DOMAIN_TOOLS: dict[str, list[str]] = {
    "shopping": [
        "get_fridge_inventory", "add_fridge_item", "remove_fridge_item",
        "record_shopping", "generate_shopping_list",
        "compare_supermarket_prices", "search_product_prices",
    ],
    "meal": [
        "search_recipes", "get_recipe_detail", "generate_meal_plan",
        "match_recipes_by_ingredients", "search_recipe_videos",
        "get_fridge_inventory",                    # ← 跨域共享
    ],
    "appliance": [...], "maintenance": [...],
    "security": [...], "household": [...],
}
```

**效果对比**：

| | 无路由（40 工具） | 有路由（8-12 工具） |
|---|---|---|
| Tool definitions tokens | ~8000 | ~2000 |
| LLM 工具选择准确率 | ~85% | ~95% |
| 每次请求成本 | 基线 | 降低 ~50% |
| 伪影（选择不该用的工具） | 常见 | 罕见 |

### 5.3 路由 LLM Prompt 设计

```
你是意图路由器。分析用户消息，输出一个领域标签。

标签：shopping | meal | appliance | maintenance | security | household | general

规则：
- 只输出一个标签，不要解释
- "冰箱里有什么" → shopping
- "规划菜谱/今天吃什么" → meal
- "打开空调/错峰运行" → appliance
- "维修/账单/缴费" → maintenance
- "门窗/安防/监控" → security
- "快递/日程/通知" → household
```

**关键设计决策**：
- `max_tokens=20`：不浪费 Token，只输出一个词
- `temperature=0`：确定性输出，确保一致性
- 规则引擎 + LLM 兜底：减少 LLM 调用频率，降低延迟和成本

---

## 6. RAG 检索增强生成数据结构

### 6.1 四阶段检索流水线

```
┌─────────────────────────────────────────────────┐
│          Phase 0: Query 增强                     │
│   Query Rewrite: 1个查询 → 3-5个改写查询         │
│   HyDE: 生成假设答案作为额外查询向量              │
├─────────────────────────────────────────────────┤
│          Phase 1: 多路并行召回                    │
│   Dense (BGE-M3 1024d)       BM25 (jieba)       │
│   ┌──────────────────┐   ┌─────────────────┐    │
│   │ Qdrant.search()   │   │ BM25Okapi       │    │
│   │ cosine similarity  │   │ TF-IDF scoring  │    │
│   │ 多查询加权融合     │   │ 关键词匹配      │    │
│   └────────┬─────────┘   └────────┬────────┘    │
│            │ candidate_k=20       │             │
├────────────┴──────────────────────┴─────────────┤
│          Phase 2: RRF 融合                       │
│   RRF = α/(k+d_rank) + (1-α)/(k+b_rank)         │
│   α=0.7（Dense 主导），k=60                       │
├─────────────────────────────────────────────────┤
│          Phase 3: Cross-Encoder 精排              │
│   BGE-Reranker-v2-m3                             │
│   final_score = RRF × 0.3 + Rerank × 0.7         │
│   Top-5 最终返回                                  │
├─────────────────────────────────────────────────┤
│          Phase 4: 质量过滤                       │
│   dense_score ≥ 0.35 阈值                        │
│   元数据过滤 + Fallback LLM-only 模式             │
└─────────────────────────────────────────────────┘
```

### 6.2 RRF (Reciprocal Rank Fusion) 公式

```
RRF(doc) = Σ α_r / (k + rank_r(doc))
           r ∈ {dense, bm25}

其中:
  k = 60           （平滑参数，避免 1/rank 的分母过小）
  α_dense = 0.7    （向量检索权重）
  α_bm25 = 0.3     （关键词检索权重）
```

### 6.3 RAG 查询结果结构

```python
{
    "question": "怎么做红烧肉?",
    "answer": "根据知识库记录，红烧肉的做法如下... [文档1]",
    "context": "[文档1](相关度:0.87) 红烧肉做法...",
    "sources_count": 3,
    "sources": [
        {"text": "红烧肉的做法:..."[:300], "score": 0.87,
         "metadata": {"source": "recipe_cookbook"}},
    ],
    "is_reliable": True,       # Self-RAG 自省结果
    "fallback": False,         # True → 知识库无结果，LLM 直接回答
}
```

### 6.4 Self-RAG 自省检查

```python
async def _reflect(question, context, answer) -> bool:
    """判断答案是否完全基于参考信息 —— 检测幻觉"""
    # LLM 回答 YES 或 NO，YES → 答案有据可查
```

### 6.5 文档摄入数据结构

```python
# 摄入流水线：清洗 → 去重（MD5） → 质量检测 → 语义分块 → 向量化 → 入库
{
    "ingested": 12,              # 摄入的 chunk 数量
    "chunks": ["分块1...", ...], # 前 3 个 chunk 预览
    "chunk_ids": ["uuid5-1", ...],
    "source": "recipe_cookbook",
}
# 质量检测：有效字符占比 ≥ 30%；中文占比 ≥ 10%（否则视为乱码）
# 清洁：全角→半角 + 多余空白合并
```

---

## 7. 向量存储与 Embedding 抽象

### 7.1 EmbeddingGenerator —— 四层降级策略

```python
class EmbeddingGenerator:
    """
    推荐层级（自动降级）：
      1. FlagEmbedding BGEM3FlagModel（Dense+Sparse，FP16，原生）
      2. ONNX Runtime（CPU 优化，2-3x 加速）
      3. sentence-transformers（通用降级）
      4. OpenAI API（最后备选，仅 Dense）
    全部不可用 → 返回零向量（系统仍可运行，但检索质量差）
    """
    _model_type: str  # "flagembedding" | "onnx" | "sentence_transformers" | "openai_api"
    _query_cache: dict[str, list[float]]  # LRU 512 条，命中率 40-60%
```

### 7.2 BGE-M3 输出结构（Dense + Sparse 双路）

```python
{
    "dense_vecs": [[0.12, -0.34, ..., 0.78], ...],  # 1024 维 float32
    "sparse_vecs": [{"冰箱": 0.8, "食材": 0.6, "库存": 0.5}, ...],  # 稀疏词权重
}
```

**为什么 Dense + Sparse 都重要？**

| 查询类型 | Dense 表现 | Sparse 表现 | 融合后 |
|----------|:---:|:---:|:---:|
| "红烧肉怎么做" | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| "冰箱温度设置" | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| "B-123 空调滤网" | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

精确术语匹配 → BM25 更强；语义相似 → Dense 更强。

### 7.3 VectorStore —— Qdrant + Fallback

```python
class VectorStore:
    collection_name: str      # "household_memory"
    _dim: int                  # 1024（BGE-M3）
    _fallback_store: list[dict] # Qdrant 不可用时的内存降级方案

# Qdrant Point 结构
PointStruct(
    id="uuid_hex_16",                    # 文档唯一 ID
    vector=[0.12, -0.34, ..., 0.78],     # 1024 维 dense vector
    payload={
        "text": "红烧肉的做法: 1.焯水...",  # 原始文本
        "user_id": "user_001",            # 多租户隔离
        "type": "memory_consolidation",    # 类型标签（用于过滤）
        "timestamp": "2026-07-31T10:00:00",
        "ttl_days": 90,
    }
)
```

### 7.4 向量数据库选型对比

| 方案 | 规模 | 检索方式 | 成本 |
|------|------|---------|------|
| Qdrant（你的方案） | <1000万 | Cosine | 免费，自托管 |
| pgvector（Postgres） | <100万 | L2/Cosine/IP | 免费（已有 PG） |
| Milvus | >1亿 | 多种 | 中等 |
| Pinecone | 任意 | Cosine/Dot | 托管费 |
| Chroma | <10万 | Cosine | 免费，轻量 |

---

## 8. Multi-Agent 编排与通信协议

### 8.1 你的架构演进：从 Multi-Agent 到 Unified

```
之前（v5.0）:
  ShoppingAgent + MealAgent + ApplianceAgent +
  MaintenanceAgent + SecurityAgent + HouseholdAgent
  → AgentCoordinator（编排/路由）
  问题：Agent 间通信开销大，上下文传递有损耗，编排逻辑复杂

现在（v5.5）:
  UnifiedAgent（单一 Agent，40+ 工具）
  → LLM 自行决策调用哪些工具
  优势：无需 Agent 间通信，上下文完整，维护简单
```

### 8.2 业界主流编排框架对比

**① LangGraph —— 图状 Agent 编排**：

```python
class AgentState(MessagesState):
    """状态在节点间流动 —— 函数式数据流"""
    current_task: str
    task_results: dict
    next_agent: str

graph = StateGraph(AgentState)
graph.add_node("planner", planner_agent)
graph.add_node("executor", executor_agent)
graph.add_conditional_edges("executor", decide_next, {
    "done": END, "review": "reviewer", "retry": "executor",
})
```

**② CrewAI —— 角色分工 + 顺序/层级执行**：

```python
crew = Crew(
    agents=[researcher, writer],
    tasks=[Task(...), Task(...)],
    process=Process.sequential,  # sequential | hierarchical
)
# 核心数据结构: Task {description, expected_output, agent, context: list[Task]}
```

**③ AutoGen —— 对话驱动编排**：

```python
# Agent 之间通过标准 OpenAI 消息格式通信
user_proxy.initiate_chat(assistant, message="帮我写一个排序函数")
# 核心: ConversableAgent.generate_reply(messages=...)
```

**④ OpenAI Agents SDK —— Handoff 委托**：

```python
household_agent = Agent(
    name="Household",
    handoffs=[fridge_agent, meal_agent],  # 可委托给子 Agent
    tools=[...],
)
result = await Runner.run(household_agent, "冰箱里有什么?")
# 核心: Handoff —— Agent 在运行中把控制权委托给另一个 Agent
```

### 8.3 业界前沿 —— Hierarchical Agent Teams（Google A2A）

2025 年提出的层级 Agent 团队模型：

```
              ┌────────────────┐
              │  Supervisor     │ ← 协调者：分解任务、分配、汇总
              │  Agent          │
              └───────┬────────┘
         ┌────────────┼────────────┐
    ┌────┴────┐  ┌────┴────┐  ┌────┴────┐
    │Shopping │  │  Meal   │  │Security │  ← 专职 Agent
    │ Agent   │  │  Agent  │  │  Agent  │
    └─────────┘  └─────────┘  └─────────┘

通信协议:
  Supervisor → Specialist: TaskAssignment {task_id, description, context, deadline}
  Specialist → Supervisor: TaskResult {task_id, status, output, artifacts}
```

这与你的 v5.0 架构几乎一致。如果未来接入更多 IoT 设备和用户，层级 Agent 模型可能再次适用。

---

## 9. Agent 安全护栏与确认机制

### 9.1 三级危险等级

```python
danger_level: Literal["safe", "caution", "dangerous"]

# safe:      纯读取，无副作用（get_fridge_inventory, check_door_status）
# caution:   有副作用但不影响物理安全（send_notification, send_bill_reminder）
# dangerous: 影响物理世界/安全（set_away_mode, control_smart_appliance）
```

### 9.2 确认流程（完整的人机协同决策回路）

```
用户: "帮我布防离家模式"
    ↓
Agent: set_away_mode() → danger_level="dangerous"
    → _call_tool 返回 {"requires_confirmation": True, ...}
    ↓
Agent: 停止 ReAct 循环
    → AgentResponse(requires_confirmation=True, pending_dangerous_calls=[...])
    ↓
前端: 展示确认弹窗 → 用户点击"确认"
    ↓
前端: 重新发送 AgentRequest(message="...", confirmed_tools=[...])
    ↓
Agent: _call_tool(set_away_mode, ..., confirmed_dangerous=True) → 正常执行
```

### 9.3 业界对比 —— Anthropic Constitutional AI

Anthropic 提出让 Agent 遵守"宪法"原则 —— 执行前 LLM 自我审查：

```
宪法条款示例:
  1. 不得执行可能导致人身伤害的操作
  2. 涉及财产变动（>¥1000）需要用户确认
  3. 涉及个人隐私数据访问需要明确授权
```

你的 `danger_level` 是规则级的（刚性），加上宪法式 LLM 自我审查可实现更灵活的安全判断 —— 比如 LLM 可能判断某个看似 `safe` 的操作在特定上下文中实际是危险的。

---

## 10. 追踪、可观测性与 Token 审计

### 10.1 TraceRecord —— 全链路追踪

```python
class TraceRecord(Base):
    __tablename__ = "agent_traces"

    trace_id: str        # "trc_a1b2c3d4e5f6"
    session_id: str      # 关联到具体会话
    user_id: str         # 多租户隔离
    agent_name: str      # "unified_household_agent"
    intent: str          # "meal" / "shopping" / ...
    user_message: str    # 用户原始消息（截断 500）
    iteration: int       # ReAct 循环第几轮
    step_type: str       # llm_call / tool_call / tool_result / final / error
    detail: JSON         # 具体内容（工具名/参数/结果摘要/token数）
    duration_ms: int     # 此步耗时
    created_at: datetime
```

### 10.2 TokenUsageRecord —— 成本审计

```python
class TokenUsageRecord(Base):
    __tablename__ = "token_usage"

    record_id: str
    user_id: str / session_id: str
    model: str               # "deepseek-v4-pro"
    prompt_tokens: int / completion_tokens: int / total_tokens: int
    estimated_cost_cny: float  # 估算人民币费用
    endpoint: str               # "/api/v1/agent/chat"

# Token 计费公式:
TOKEN_PRICES = {
    "deepseek-chat": {"prompt": 1.0, "completion": 2.0},       # 元/百万tokens
    "deepseek-reasoner": {"prompt": 4.0, "completion": 16.0},
    "gpt-4o": {"prompt": 18.0, "completion": 54.0},
}
cost = prompt/1e6 * price["prompt"] + completion/1e6 * price["completion"]
```

### 10.3 FeedbackRecord —— 质量反馈闭环

```python
class FeedbackRecord(Base):
    __tablename__ = "user_feedback"

    feedback_id: str
    session_id: str / user_id: str / trace_id: str
    user_message: str / agent_response: str
    rating: str             # positive / negative / neutral
    comment: str            # 用户补充说明
```

### 10.4 业界前沿 —— Langfuse / OTEL for LLMs

```python
# Langfuse Trace 模型（嵌套 Observation 比扁平列表更具表现力）
Trace(
    observations=[
        Observation(name="llm_call", type="generation",
                    model="deepseek-v4-pro", usage={"prompt_tokens": 1200}),
        Observation(name="tool_call", type="span",
                    input={"tool": "get_fridge_inventory"}, output=result),
    ]
)

# OpenTelemetry 语义约定
Span {
    name: "chat deepseek-v4-pro",
    attributes: {
        "llm.request.model": "deepseek-v4-pro",
        "llm.usage.prompt_tokens": 1200,
        "agent.name": "unified_household_agent",
        "session.id": "sess_uuid",
    }
}
```

你的 `TraceRecord` 已覆盖这些关键字段。如果启用 OpenTelemetry（settings 中已有 `otel_enabled`），可直接导出到 Langfuse/Jaeger。

---

## 11. Plan-and-Execute 与层次化规划

### 11.1 当前方案：轻量级 LLM 计划生成

```python
async def _generate_plan(user_message, context) -> list[str] | None:
    """检测复杂任务 → LLM 分解为有序子任务"""

    # 快速判断：太短或单一意图 → 跳过
    if len(msg) < 15: return None

    # 多意图关键词检测
    if not any(kw in msg for kw in ["然后", "接着", "再", "顺便"]):
        return None

    # LLM 分解 → "1. 检查冰箱库存\n2. 推荐菜谱\n3. 生成购物清单"
    return steps[:5]
```

生成的计划注入 system prompt：

```
## 执行计划
用户的任务已分解为以下步骤，请按顺序逐步执行：
  1. 检查冰箱库存
  2. 根据库存推荐菜谱
  3. 生成购物清单
  4. 比较价格并推荐最优超市

每完成一步后再开始下一步，不要跳过。
```

### 11.2 业界前沿 —— 结构化 Plan-and-Execute（LangGraph）

```
                 ┌──────────────┐
                 │   Planner    │ → Plan {steps: [Step1, Step2, ...]}
                 └──────┬───────┘
                        │ plan
                 ┌──────┴───────┐
                 │  Executor    │ → 执行当前 step
                 └──────┬───────┘
                        │ result
                 ┌──────┴───────┐
                 │  Replanner   │ → 继续/重规划/完成
                 └──────────────┘

数据结构:
  Plan { steps: [Step{description, status, result}], current_idx: int }
  Step { description: str, status: "pending"|"running"|"done"|"failed",
         result: str, depends_on: list[int] }
```

**关键区别**：你的方案中计划只是文本注入，LLM"被建议"按计划执行。真正的 P&E 中计划是结构化数据，执行器逐条执行并记录状态，Replanner 可动态修改未执行步骤。

### 11.3 业界前沿 —— Tree of Thoughts (ToT)

比 Plan-and-Execute 更高级 —— 不是一条线性计划，而是多分支的思维树：

```
             ┌── 鸡蛋+番茄 → 推荐番茄炒蛋（匹配度 3/4）
             │
用户: 做什么菜? ──┼── 鸡蛋+牛奶 → 推荐蒸蛋（匹配度 2/4）
             │
             └── 鸡蛋+葱 → 推荐葱花炒蛋（匹配度 3/4）

每个节点: Thought { text: str, evaluation: float, children: list[Thought] }
BFS/DFS 搜索最优路径，每步 LLM 评估: "这个思路可行吗？（1-10 分）"
```

你的系统目前未使用 ToT，但在多步骤规划+评估场景中可引入 —— 如"规划本周菜谱"时，LLM 生成 3 种方案，评估均衡性、利用率、预算友好度，选最优。

---

## 12. 业界前沿：Agent 协议与标准

### 12.1 Anthropic MCP（2024年11月发布）

定义了 AI 模型与外部工具的标准化通信协议。核心创新：不只是函数调用，而是把**资源（Resources）**和**提示词模板（Prompts）**也作为可发现的服务暴露：

```
┌──────────┐  JSON-RPC 2.0   ┌──────────┐
│  LLM     │ ◄──────────────► │  MCP     │
│  (Claude)│                  │  Server  │
└──────────┘                  └────┬─────┘
                                   │
                     ┌─────────────┼─────────────┐
                ┌────┴────┐  ┌────┴────┐  ┌────┴────┐
                │ DB Tool │  │FS Tool  │  │API Tool │
                └─────────┘  └─────────┘  └─────────┘

核心数据结构:
  tools/list → {tools: [{name, description, inputSchema}]}
  tools/call → {name, arguments} → {content: [{type: "text", text: "..."}]}
  resources/list → {resources: [{uri, name, description, mimeType}]}
  prompts/list → {prompts: [{name, description, arguments}]}
```

### 12.2 Google A2A（2025年4月发布）

定义了 Agent 之间的标准化通信协议。核心概念：`AgentCard`（自描述）、`Task`（任务传递）、`Artifact`（任务产出）：

```json
// Agent Card（Agent 的自描述）
{"name": "HouseholdAgent", "url": "https://api.example.com/a2a",
 "skills": [{"id": "meal_planning", "name": "膳食规划"}],
 "capabilities": {"streaming": true}}

// Task（Agent 间的任务传递）
{"id": "task_uuid", "sessionId": "sess_uuid",
 "status": {"state": "working"},
 "history": [{"role": "user", "parts": [{"type": "text", "text": "今晚吃什么?"}]}]}

// Artifact（任务产出）
{"artifactId": "uuid", "parts": [
  {"type": "text", "text": "推荐: 番茄炒蛋"},
  {"type": "data", "data": {"recipe": {...}}, "mimeType": "application/json"}
]}
```

**A2A 的启示**：如果你的系统未来需要与其他 AI Agent 协作，A2A 提供了标准化蓝图。`AgentCard` 类似于 `UnifiedAgent.description`，`Task` 类似于 `AgentRequest`，`Artifact` 类似于 `data` 字段。

### 12.3 OpenAI Agents SDK（2025年3月发布）

```python
class Agent:
    name: str / instructions: str
    tools: list[Tool] / handoffs: list[Agent]  # 可委托子 Agent
    input_guardrails: list[Guardrail] / output_guardrails: list[Guardrail]
    output_type: type              # 结构化输出类型（Pydantic）

class RunResult:
    final_output: Any / last_agent: Agent
    raw_responses: list[Response] / new_items: list[ResponseItem]
```

**关键对比**：

| 概念 | Agent of Life | OpenAI Agents SDK |
|------|--------------|-------------------|
| Agent 定义 | `BaseAgent(name, system_prompt, tools)` | `Agent(name, instructions, tools)` |
| 执行 | `agent.run(request) → AgentResponse` | `Runner.run(agent, input) → RunResult` |
| 安全护栏 | `danger_level` + `confirmed_tools` | `input_guardrails` / `output_guardrails` |
| 子 Agent | n/a（合并为 Unified） | `handoffs: list[Agent]` |
| 结构化输出 | n/a | `output_type: Pydantic` |

---

## 13. 数据结构选型决策框架

### 13.1 消息协议选型

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| 单个 LLM + 工具的 Agent | OpenAI Chat Completions 格式 | 最广泛支持 |
| 多模型支持（DeepSeek + GPT + Claude） | OpenAI 格式 + 适配层 | 你的系统已实现 |
| Agent-to-Agent 通信 | A2A 协议或 AutoGen 消息模型 | 标准化，跨组织 |
| 前端 ↔ Agent 通信 | 自定义 Pydantic 协议 | 类型安全，前端友好 |

### 13.2 记忆系统选型

| 场景 | 推荐方案 |
|------|---------|
| 单会话记忆（几十条消息） | 内存 dict（有 Redis 备份） |
| 多会话记忆（跨天） | Redis + 向量库，自动摘要固化 |
| 大规模用户（百万级） | Redis Cluster + 分布式向量库（Milvus/Pinecone） |
| 需要结构化记忆（关系推理） | 向量检索 + 知识图谱（Neo4j） |
| 需要精确记忆（如偏好、过敏物） | PostgreSQL JSON 字段 + 确定性查询 |

### 13.3 向量存储选型

| 规模 | 方案 | 成本 |
|------|------|------|
| < 10 万条 | Qdrant（你的方案） | 免费 |
| 10 万 ~ 100 万 | Qdrant / pgvector | 免费~低 |
| 100 万 ~ 1 亿 | Milvus / Pinecone | 中等 |
| > 1 亿 | Elasticsearch + 向量插件 | 高 |

### 13.4 Agent 编排模式选型

| 模式 | 适用场景 | 代表框架 |
|------|---------|---------|
| 统一 Agent（你的方案） | 工具 ≤ 50，任务 ≤ 6 域 | OpenAI Agents SDK |
| 顺序编排（Sequential） | 固定流程：分析→执行→检查 | CrewAI Sequential |
| 层级编排（Hierarchical） | 复杂任务需专业子 Agent | LangGraph Supervisor |
| 对话驱动编排 | Agent 间自由对话协作 | AutoGen |
| 事件驱动编排 | 异步、解耦、可扩展 | Event-driven Agent |

---

## 附录 A：Agent of Life v5.5 完整数据模型清单

### A.1 Agent 通信模型

| 模型 | 文件 | 用途 |
|------|------|------|
| `AgentRequest` | [schemas.py](backend/app/models/schemas.py) | 用户→Agent 请求 |
| `AgentResponse` | [schemas.py](backend/app/models/schemas.py) | Agent→用户响应 |
| `ConversationMessage` | [schemas.py](backend/app/models/schemas.py) | 对话原子消息 |
| requires_confirmation | [schemas.py](backend/app/models/schemas.py) | 安全确认协议 |

### A.2 业务域模型（10 个 Pydantic 模型）

| 模型 | 用途 |
|------|------|
| `UserProfile` | 用户画像（偏好/过敏物/预算） |
| `FamilyMember` | 家庭成员 |
| `Appliance` / `ApplianceType` | 家电信息与类型枚举 |
| `Ingredient` | 食材（数量/过期日/营养） |
| `Recipe` | 菜谱（做法/难度/标签） |
| `ShoppingItem` / `ShoppingList` | 购物清单 |
| `MealPlan` | 膳食计划 |
| `MaintenanceTask` | 维保任务 |
| `SecurityEvent` | 安防事件 |
| `HouseholdTask` | 家庭事务 |

### A.3 记忆/向量/RAG 模型

| 结构 | 用途 |
|------|------|
| `MemoryEntry`（Pydantic） | 长期记忆单元 |
| `ConversationMemory._memory`（dict+Redis） | 短期记忆 |
| `messages: list[dict]`（LLM Context） | 工作记忆 |
| `ToolRegistry._tools`（dict） | 全局工具注册表 |
| `PointStruct`（Qdrant） | 向量存储单元 |
| `sources: list[dict]` | RAG 检索结果 |

### A.4 追踪与审计模型

| 模型 | 表 | 用途 |
|------|------|------|
| `TraceRecord` | `agent_traces` | ReAct 全链路追踪 |
| `TokenUsageRecord` | `token_usage` | Token 用量/成本审计 |
| `FeedbackRecord` | `user_feedback` | 用户反馈收集 |

### A.5 数据库表总览（11 张表 + 2 外部存储）

| 存储 | 表/集合 | 用途 |
|------|------|------|
| PostgreSQL | `users` | 用户档案 |
| PostgreSQL | `fridge_items` | 冰箱食材 |
| PostgreSQL | `shopping_records` | 购物记录 |
| PostgreSQL | `meal_plans` | 菜谱计划 |
| PostgreSQL | `appliances` | 家电信息 |
| PostgreSQL | `maintenance_tasks` | 维保任务 |
| PostgreSQL | `agent_traces` | Agent 执行追踪 |
| PostgreSQL | `user_feedback` | 用户反馈 |
| PostgreSQL | `token_usage` | Token 用量 |
| PostgreSQL | `tracking_numbers` | 快递单号 |
| Redis | `conv:{session_id}` | 对话历史（List, TTL 7天） |
| Qdrant | `household_memory` | 向量记忆（1024维, Cosine） |

### A.6 全局单例清单（9 个）

| 单例 | 函数 | 用途 |
|------|------|------|
| `HouseholdCrew` | `get_household_crew()` | Agent 编排器 |
| `UnifiedAgent` | `get_unified_agent()` | 统一家务 Agent |
| `IntentRouter` | `get_intent_router()` | 意图路由器 |
| `ConversationMemory` | `get_conversation_memory()` | 对话记忆管理 |
| `VectorStore` | `get_vector_store()` | 向量存储 |
| `EmbeddingGenerator` | `get_embedding_generator()` | 向量嵌入生成 |
| `HybridRetriever` | `get_retriever()` | 混合检索引擎 |
| `RAGChain` | `get_rag_chain()` | RAG 问答链 |
| `Settings` | `settings` | 全局配置 |

---

## 附录 B：业界框架核心类型速查

### B.1 LangChain 核心类型

```python
class BaseMessage: content: str; type: str  # "human"|"ai"|"system"|"tool"
class ToolCall: name: str; args: dict; id: str
class AgentAction: tool: str; tool_input: dict; log: str
class AgentFinish: return_values: dict; log: str
class Document: page_content: str; metadata: dict
```

### B.2 CrewAI 核心类型

```python
class Agent: role: str; goal: str; backstory: str; tools: list[BaseTool]
class Task: description: str; expected_output: str; agent: Agent; context: list[Task]
class Crew: agents: list[Agent]; tasks: list[Task]; process: Process
```

### B.3 AutoGen 核心类型

```python
class ConversableAgent: name: str; system_message: str; llm_config: dict
class ChatResult: chat_id: str; chat_history: list[dict]; summary: str; cost: dict
```

### B.4 LlamaIndex 核心类型

```python
class Node(BaseNode): text: str; embedding: list[float]; score: float; metadata: dict
class QueryBundle: query_str: str; embedding: list[float]
class Response: response: str; source_nodes: list[NodeWithScore]; metadata: dict
```

---

> **编写日期**：2026-07-31
> **适用版本**：Agent of Life v5.5
> **参考框架**：OpenAI Agents SDK, Anthropic MCP, Google A2A, LangChain, CrewAI, AutoGen, LlamaIndex, LangGraph, MemGPT/Letta, Infini-Attention
> **关键词**：Agent Architecture, Data Structures, ReAct, RAG, Function Calling, Memory System, Multi-Agent, Vector Store, Tracing, Safety Guardrails
