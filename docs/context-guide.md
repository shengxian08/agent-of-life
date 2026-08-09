# 📝 LLM 上下文管理完全指南

> 上下文是大模型"看到"的全部内容。上下文的质量，直接决定了回答的质量。

---

## 目录

1. [什么是"上下文"？](#1-什么是上下文)
2. [Messages 数组 — LLM 看到的全部](#2-messages-数组--llm-看到的全部)
3. [System Prompt — 给模型的"人格设定"](#3-system-prompt--给模型的人格设定)
4. [上下文窗口 Context Window — 模型的内存上限](#4-上下文窗口-context-window--模型的内存上限)
5. [Token — 上下文的基本单位](#5-token--上下文的基本单位)
6. [为什么上下文会"爆炸"？](#6-为什么上下文会爆炸)
7. [上下文管理策略概览](#7-上下文管理策略概览)
8. [策略一：滑动窗口 Sliding Window](#8-策略一滑动窗口-sliding-window)
9. [策略二：摘要压缩 Summarization](#9-策略二摘要压缩-summarization)
10. [策略三：记忆注入 Memory Injection](#10-策略三记忆注入-memory-injection)
11. [策略四：意图路由 — 缩减工具上下文](#11-策略四意图路由--缩减工具上下文)
12. [策略五：Plan-and-Execute](#12-策略五plan-and-execute)
13. [一个完整的上下文组装过程（本项目实战）](#13-一个完整的上下文组装过程本项目实战)

---

## 1. 什么是"上下文"？

### 用一个比喻

把 LLM 想象成一个**失忆的专家**：

```
每次跟你对话时，你必须把以下内容重新告诉他：

  ┌─────────────────────────────────────────┐
  │  👤 你是谁（System Prompt）              │
  │     "你是一个家务AI管家..."              │
  │                                          │
  │  👤 用户是谁（用户档案）                  │
  │     "张三，三口之家，不吃辣..."           │
  │                                          │
  │  💬 之前聊了什么（对话历史）               │
  │     用户: 冰箱里有什么？                  │
  │     助手: 您冰箱里有菠菜、鸡胸肉...       │
  │     用户: 菠菜能做什么菜？  ← 新问题     │
  └─────────────────────────────────────────┘
         ↑ 这些全部，就是"上下文"
```

**如果你不告诉他之前聊了什么，他就不知道"菠菜"是哪来的**——因为他没有记忆，每次对话都像第一次见面。

### 技术定义

在 OpenAI 兼容的 API 中，上下文就是 `messages` 数组：

```json
{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "你是家务AI管家..."},
    {"role": "user", "content": "冰箱里有什么？"},
    {"role": "assistant", "content": "您冰箱里有菠菜、鸡胸肉..."},
    {"role": "user", "content": "菠菜能做什么菜？"}
  ]
}
```

**每次 API 调用，你必须把全部上下文重新发送一遍。** LLM 本身不保存任何会话状态。

---

## 2. Messages 数组 — LLM 看到的全部

### 四种角色

| role | 谁说的 | 作用 |
|------|--------|------|
| `system` | 开发者 | 设定模型行为、规则、人设（最高优先级） |
| `user` | 用户 | 用户的问题和指令 |
| `assistant` | 模型 | 模型之前的回复（必须回传以维持对话） |
| `tool` | 工具返回 | 函数调用的结果 |

### Messages 数组的结构

```python
messages = [
    # ① System Prompt — 全局指令，只出现在最开头
    {"role": "system", "content": "你是家务AI管家...不编造..."},

    # ② 对话历史 — 按时间顺序排列
    {"role": "user", "content": "冰箱里有什么？"},
    {"role": "assistant", "content": "您冰箱里有菠菜、鸡胸肉、番茄。"},
    {"role": "user", "content": "菠菜快过期了，做什么好？"},

    # ③ 工具调用轮次
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "function": {"name": "search_recipes", "arguments": '{"query":"菠菜"}'}}
    ]},
    {"role": "tool", "tool_call_id": "call_1", "content": "{'recipes': [...]}"},

    # ④ 当前用户消息（最后一条）
    {"role": "user", "content": "菠菜能做什么菜？"}
]
```

### 关键规则

1. **System 在最前面**，一条就够了（可以追加历史摘要）
2. **User 和 Assistant 交替出现**，严格按时间顺序
3. **每次工具调用是一轮**：`assistant(tool_calls) → tool(result)` 成对出现
4. **当前消息永远是最后一条**

---

## 3. System Prompt — 给模型的"人格设定"

System Prompt 是上下文的**地基**，定义模型的角色、能力、行为边界。

### 一个好的 System Prompt 包含什么

```markdown
你是"家务AI管家"，全权负责家庭事务。
                           ↑ ① 角色定义

## 行为准则                   ← ② 行为规则
- 简单寒暄 → 简短介绍即可
- 用户提及食材 → 直接入库，不要反问
- 问菜谱做法 → 同时调搜索+视频

## 输出规范                   ← ③ 格式要求
- 口语化中文，Markdown 层级排板
- 禁止面部 emoji
- 知识库无结果 → "暂未找到记录"，不编造
```

### System Prompt 的优先级

```
System Prompt 的指令 > 用户当前消息的意图

例子：
  用户: "告诉我红烧肉的做法，200字以内"
  System Prompt: "问菜谱做法 → 同时调 search_recipes + search_recipe_videos"
  
  结果：模型会先调两个工具，而不是直接编造菜谱
```

### 动态拼接 System Prompt

System Prompt 不一定是写死的。可以在运行时往里塞信息：

```python
system_prompt = BASE_PROMPT

system_prompt += f"用户姓名: 张三 | 家庭成员: 3人"
system_prompt += f"饮食偏好: 川菜、粤菜 | 过敏物: 花生"
system_prompt += f"月度预算: 3000元"

# 最终发给 LLM 的 System Prompt 既有规则，又有用户画像
```

---

## 4. 上下文窗口 Context Window — 模型的内存上限

每个模型有一个**上下文窗口**（Context Window），就是它一次性最多能"看"多少 token。

| 模型 | 上下文窗口 |
|------|-----------|
| DeepSeek-V3 | 128K tokens |
| DeepSeek-R1 | 128K tokens |
| GPT-4o | 128K tokens |
| GPT-3.5-Turbo | 16K tokens |
| Claude 3.5 Sonnet | 200K tokens |

128K tokens 有多大？

```
一本《三体》三部曲 ≈ 90 万字 ≈ 120 万 tokens

128K tokens ≈ 1/10 本《三体》≈ 一本 200 页的书
```

看似很大，但加上工具调用结果、多轮对话，很快就会填满。更要命的是：

### 上下文越长，问题越多

```
长上下文的问题：

  ❌ 成本翻倍 — 每次请求都要为全部 token 付费
  ❌ 延迟增加 — 处理 100K token 比 1K token 慢得多
  ❌ 注意力稀释 — 模型"记不住"上下文中间的内容
     （Lost in the Middle 现象：开头和结尾的信息记得最牢，中间的被忽略）
  ❌ 幻觉增多 — 信息太多时模型更容易编造
```

所以**上下文管理的核心目标不是"塞更多"，而是"留精华"**。

---

## 5. Token — 上下文的基本单位

Token 是 LLM 处理文本的最小单位，不等于"字"。

```
中文:  "我是AI管家"
       → ["我", "是", "AI", "管家"]  → 4 tokens
       大约 1 个汉字 ≈ 1~2 个 token

英文:  "I am an AI butler"
       → ["I", " am", " an", " AI", " butler"]  → 5 tokens
       大约 1 个单词 ≈ 1~1.5 个 token

代码:  "await asyncio.gather(*tasks)"
       → 约 6 tokens

Emoji: "😊" → 1~3 tokens
```

### 为什么这是底线知识？

因为**计价按 token、窗口按 token、一切优化都要算 token**：

```
输入价格: DeepSeek-V3 → 1 元 / 100 万 tokens
输出价格: DeepSeek-V3 → 2 元 / 100 万 tokens

如果每次请求塞满 128K tokens:
  成本 = 128K × 1 / 100万 ≈ 0.128 元/次
  一天 1000 次 = 128 元/天
  一个月 = 3840 元

如果把上下文压缩到 8K tokens:
  成本 = 8K × 1 / 100万 ≈ 0.008 元/次
  一天 1000 次 = 8 元/天
  一个月 = 240 元

差距：16 倍！
```

---

## 6. 为什么上下文会"爆炸"？

一个真实的多轮 ReAct Agent 对话，上下文的膨胀速度：

```
第 1 轮对话:
  用户: "冰箱里有什么？"
  → System Prompt (1K tokens) + 1 组对话 (0.3K) = 1.3K tokens ✅

第 3 轮对话（含工具调用）:
  用户: "菠菜能做什么菜？"
  System Prompt (1K) + 历史 2 轮 (1K) +
  LLM 思考 + 工具调用请求 (0.2K) +
  工具返回结果 (2K) +                          ← 工具结果通常很长！
  LLM 最终回复 (0.3K)
  = 4.5K tokens ⚠️

第 10 轮对话:
  System Prompt (1K) + 历史 9 轮 (15K) +
  当前工具调用返回 (2K)
  = 18K tokens 🔴

第 50 轮:
  = 80K+ tokens 💥 接近窗口上限！
```

**罪魁祸首是工具调用结果**——菜谱列表、冰箱库存、比价结果，这些 JSON 动不动就是几千 token。

---

## 7. 上下文管理策略概览

| 策略 | 解决什么问题 | 怎么做 |
|------|-------------|--------|
| 滑动窗口 | 对话太长 | 只保留最近 N 轮 |
| 摘要压缩 | 旧对话有价值但不能全保留 | LLM 把旧对话压缩成一段摘要 |
| 记忆注入 | 跨会话信息丢失 | 从向量库检索相关历史记忆 |
| 意图路由 | 工具太多，prompt 太大 | 只给模型当前意图相关的工具 |
| Plan-and-Execute | 复杂任务中间过程膨胀 | 生成执行计划引导模型 |

**一个成熟的 Agent 系统会同时使用以上所有策略。** 下面逐一展开。

---

## 8. 策略一：滑动窗口 Sliding Window

### 原理

```
完整历史（30轮对话）:
[第1轮] [第2轮] [第3轮] ... [第25轮] [第26轮] [第27轮] [第28轮] [第29轮] [第30轮]

滑动窗口（只保留最近 5 轮）:
[第1~25轮: 丢弃或压缩] [第26轮] [第27轮] [第28轮] [第29轮] [第30轮]
                                                    ↑ 保留这一段
```

### 实现

```python
MAX_FULL = 5   # 保留最近 5 轮完整内容

history = await memory.get_history(session_id)

if len(history) > MAX_FULL:
    # ① 把旧对话压缩成摘要 → 注入 System Prompt
    old_history = history[:-MAX_FULL]
    summary = await llm_summarize(old_history)
    messages.append({"role": "system", "content": f"[历史摘要] {summary}"})

# ② 最近 5 轮完整保留
for h in history[-MAX_FULL:]:
    messages.append({"role": h.role, "content": h.content})

# ③ 当前消息
messages.append({"role": "user", "content": current_message})
```

### 优缺点

| 优点 | 缺点 |
|------|------|
| 实现简单 | 旧信息永久丢失 |
| 成本可控 | 窗口太小时模型"失忆" |
| 配合摘要效果好 | 窗口大小是经验值 |

---

## 9. 策略二：摘要压缩 Summarization

### 原理

把旧对话交给 LLM，让它提炼关键信息：

```python
# 旧对话原文（2000 tokens）:
"用户: 冰箱里有什么？
 助手: 菠菜0.5斤(明天过期)、鸡胸肉1块(7/20过期)、番茄3个、鸡蛋10个
 用户: 菠菜能做什么？
 助手: 蒜蓉菠菜、菠菜蛋花汤、菠菜拌粉丝。推荐蒜蓉菠菜，做法简单...

 ↓ LLM 压缩 ↓

# 摘要（50 tokens）:
"用户冰箱有临期菠菜和鸡胸肉。助手推荐了蒜蓉菠菜。"
```

### 实现

```python
async def _summarize_history(self, dialog_text: str) -> str:
    resp = await self.client.chat.completions.create(
        model=settings.openai_model,
        messages=[{
            "role": "system",
            "content": "用一句话（不超过 100 字）总结以下对话的核心内容和达成的决策。只输出总结本身。",
        }, {
            "role": "user",
            "content": dialog_text[:2000],  # 只取前 2000 字符防止太长
        }],
        temperature=0.1,    # 低温 → 更稳定的摘要
        max_tokens=120,
    )
    return resp.choices[0].message.content.strip()
```

### 摘要 vs 原文

```
原文（2000 tokens）:
  "用户问冰箱库存，助手查询后返回3种食材：菠菜0.5斤7/19过期，
   鸡胸肉1块7/20过期，番茄3个。用户接着问菠菜做法，助手...
   （详细记录了每种食材、日期、推荐做法、步骤...）"

摘要（50 tokens）:
  "用户查询冰箱，有临期菠菜和鸡胸肉。助手推荐了蒜蓉菠菜。"

压缩比: 40:1
信息损失: 丢失了具体过期日期、其他食材、菜谱步骤
保留的: 关键事实和结论
```

**摘要是一个权衡**：用信息精度换取 token 成本。

---

## 10. 策略三：记忆注入 Memory Injection

### 滑动窗口 + 摘要只能处理"当前会话"

如果用户隔了一天回来问"上次你说的那个菠菜做法再给我看看"，滑动窗口里已经没有这段对话了。

**记忆注入**就是跨会话的信息检索：

```
当前会话之前的所有对话
        │
        ▼
  ┌─ 向量化存储 ─┐    用户问题: "上次那个菠菜做法"
  │ 对话1: ...     │         │
  │ 对话2: 菠菜...  │  ←─────┘ 语义检索 "菠菜 + 做法"
  │ 对话3: ...     │
  └────────────────┘
        │
        ▼
  检索到: "对话2: 助手推荐了蒜蓉菠菜，需要大蒜、菠菜..."
        │
        ▼
  注入到当前 System Prompt:
  "[用户历史记忆] 之前做过蒜蓉菠菜，用户喜欢..."
```

### 注入时机

```
第一次对话（用户ID首次出现）→ 注入全部历史摘要
后续对话 → 只在新问题涉及过去时才检索注入
```

---

## 11. 策略四：意图路由 — 缩减工具上下文

### 11.1 为什么需要路由？

本项目有 40+ 个工具。如果全发给 LLM：

```json
// 40 个工具 × 每个约 200 tokens 的定义 = 8000 tokens
// 而且 LLM 要从 40 个工具里选 → 选择困难，容易选错
// 选错工具 → 多余调用 → 更多 token → 恶性循环
```

所以用意图路由做预筛选：**先判断用户想干嘛，只给相关工具**。

### 11.2 三层路由架构

```
用户消息 "帮我买番茄"
        │
        ▼
  ┌─ 第 1 层: 规则匹配（0ms，零延迟）──────────┐
  │  关键词: "番茄"、"比价"、"盒马" → shopping   │
  │  命中率: ~80%                                │
  └──────────────┬──────────────────────────────┘
                 │ 未命中
                 ▼
  ┌─ 第 2 层: 缓存命中（<1ms）─────────────────┐
  │  "上上周用户问过类似的话" → 同等意图          │
  │  命中率: ~10%                                │
  └──────────────┬──────────────────────────────┘
                 │ 未命中
                 ▼
  ┌─ 第 3 层: LLM 分类（~500ms）───────────────┐
  │  轻量调用 (max_tokens=20, timeout=5s)        │
  │  命中率: ~10%（兜底）                         │
  └──────────────┬──────────────────────────────┘
                 │
                 ▼
         intent = "shopping"
                 │
                 ▼
  ┌─ 返回候选工具 ──────────────────────────────┐
  │  shopping 领域工具 (7个) + 通用工具 (4个)     │
  │  = 11 个工具，而非 40 个                      │
  │  工具定义从 8000 → ~2000 tokens（节省 75%）   │
  └──────────────────────────────────────────────┘
```

### 11.3 第一层：规则匹配（零延迟）

```python
def _rule_match(self, message: str) -> str | None:
    msg = message.strip()

    # ① 先判断是不是寒暄
    short_greetings = {"你好", "hi", "hello", "在吗", "早", "晚安", "谢谢"}
    if msg.lower() in short_greetings or len(msg) < 3:
        return "general"

    # ② 关键词 → 意图映射
    if any(kw in msg for kw in ["冰箱", "买了", "购物清单", "比价", "盒马", "永辉"]):
        return "shopping"

    if any(kw in msg for kw in ["怎么做", "菜谱", "食谱", "今天吃什么", "红烧"]):
        return "meal"

    if any(kw in msg for kw in ["空调", "洗衣机", "错峰", "省电", "预约"]):
        return "appliance"

    if any(kw in msg for kw in ["维修", "保养", "坏了", "账单", "缴费", "师傅"]):
        return "maintenance"

    if any(kw in msg for kw in ["安防", "门窗", "监控", "门锁", "布防", "离家"]):
        return "security"

    if any(kw in msg for kw in ["日程", "快递单号", "社区", "空闲", "提醒"]):
        return "household"

    # ③ 综合巡检 → general（给全部工具）
    if any(kw in msg for kw in ["巡检", "概览", "全面", "综合"]):
        return "general"

    return None   # 没命中，交给下一层
```

**为什么规则最先？**
- 零延迟（纯字符串匹配，0ms）
- 覆盖 80% 的日常场景
- 确定性 100%（不会分错类）

**为什么简单寒暄要立刻返回 `general` 而不是 `None`？**
- 因为"你好"这种消息，LLM 分类也要 500ms，没必要
- 直接给 `general` 意图 + 全部工具，反正寒暄不需要调工具，LLM 不会乱调

### 11.4 第二层：缓存命中（<1ms）

```python
# 取用户消息前 100 个字符做缓存键
cache_key = user_message.strip()[:100].lower()

if cache_key in self._intent_cache:
    return self._intent_cache[cache_key], self._get_tools(cached)

# 缓存上限 200 条，满了就删最旧的 30 条
if len(self._intent_cache) > 200:
    keys = list(self._intent_cache.keys())[:30]
    for k in keys:
        del self._intent_cache[k]
```

**缓存策略**：
- Key 是用户消息的前 100 字符（足够区分不同问题）
- 上限 200 条防止内存泄漏
- 淘汰策略是 LRU 的简化版：删最旧的 30 条

### 11.5 第三层：LLM 分类（兜底）

```python
async def _llm_classify(self, user_message: str) -> str:
    resp = await self.client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": ROUTER_PROMPT},  # 专门的分类 prompt
            {"role": "user", "content": user_message[:300]}, # 只看前 300 字
        ],
        temperature=0,       # 不需要创意，只要确定性分类
        max_tokens=20,       # 只输出一个单词，20 tokens 够用
    )
    label = resp.choices[0].message.content.strip().lower()
    # 容错：LLM 可能输出 "shopping." 或 "shopping\n" → 清洗
    label = label.split("\n")[0].strip().rstrip(".,，。")

    # 二次校验：如果 LLM 输出了不在白名单里的词 → 修正
    if label not in valid_labels:
        for valid in valid_labels:
            if valid in label or label in valid:
                return valid
        return "general"   # 彻底无法识别 → 回退

    return label
```

**为什么是轻量级调用？**

| 对比 | 正常 LLM 调用 | 路由器 LLM 调用 |
|------|-------------|----------------|
| max_tokens | 2000 | **20** |
| temperature | 0.7 | **0** |
| timeout | 60s | **5s** |
| 输出内容 | 完整回答 | **一个单词** |
| 延迟 | 1-3s | **<500ms** |

### 11.6 六大领域 → 工具映射

```python
DOMAIN_TOOLS = {
    "shopping":    [ 7 个 ]  # 冰箱库存、比价、购物清单...
    "meal":        [ 6 个 ]  # 菜谱搜索、膳食规划、视频...
    "appliance":   [ 4 个 ]  # 家电状态、错峰调度、控制...
    "maintenance": [ 5 个 ]  # 维保检查、维修师傅、账单...
    "security":    [ 6 个 ]  # 门窗监控、安防事件、老人...
    "household":   [ 6 个 ]  # 快递追踪、日程、通知...
}

COMMON_TOOLS = [           # ← 任何意图都可能用到的通用工具
    "recall_user_memory",  # 短期记忆检索
    "search_knowledge_base", # RAG 知识库检索
    "web_search",           # 互联网搜索兜底
    "analyze_image",        # 图片识别
]
```

**意图 → 工具的逻辑**：

```python
def _get_tools(self, intent: str) -> list[str]:
    if intent == "general":
        # general → 给全部工具（寒暄、综合性巡检）
        return all_domain_tools + COMMON_TOOLS  # 40 个

    # 具体意图 → 领域工具 + 通用工具
    return DOMAIN_TOOLS[intent] + COMMON_TOOLS  # 7~11 个
```

**关键细节**：`general` 意图是**全部 40 个工具**，因为用户说"帮我全面检查一下家里"时确实可能用到任何工具。其余的意图都严格限定在 7~11 个。

### 11.7 容错机制

```
规则匹配未命中
  ↓
LLM 分类失败（网络超时 / API 报错）
  ↓
→ 返回 "general"（给全部工具）
→ 虽然工具列表大了点，但至少不会拒绝服务

规则匹配和 LLM 分类都给出了不合理的标签
  ↓
→ 白名单校验 → 不在 valid_labels 里 → 修正为 "general"
→ 防御性编程：宁可给多不给错
```

**设计哲学**：路由错了比没路由更糟糕（限制了工具但分错了领域 → LLM 没有所需工具 → 回答质量下降）。所以宁可 fallback 到 general 给全量工具，也不能给错工具集。

### 11.8 路由器的效果

```
场景: 用户说 "番茄多少钱一斤？"

没有路由器:
  → 40 个工具定义发给 LLM (8000 tokens)
  → LLM 在 40 个工具里挑 → 可能选错
  → 选错 → 重试 → 更多 token

有路由器:
  → 规则匹配 "番茄" → "shopping"
  → 11 个工具发给 LLM (2000 tokens)
  → LLM 在 11 个工具里挑 → 准确率大幅提升
  → 一次命中 → 少调工具

节省: 75% 工具定义 token + 减少无效工具调用
```

---

## 12. 策略五：Plan-and-Execute

### 问题

复杂任务（如"检查冰箱库存，规划本周菜谱，生成购物清单，预约今晚错峰运行"）会产生超长的中间过程，每步的工具调用和结果都在膨胀上下文，到后面模型都忘了最开始要干什么。

### 解决：先规划，再执行

```python
# 第 0 步：生成执行计划（注入 System Prompt）
plan = [
    "1. 检查冰箱库存",
    "2. 根据库存规划本周菜谱",
    "3. 对比库存和菜谱生成购物清单",
    "4. 预约今晚错峰运行家电",
]

# System Prompt 末尾追加:
"""
## 执行计划
用户的任务已分解为以下步骤，请按顺序逐步执行：
  1. 检查冰箱库存
  2. 根据库存规划本周菜谱
  3. 对比库存和菜谱生成购物清单
  4. 预约今晚错峰运行家电

每完成一步后再开始下一步，不要跳过。
"""
```

效果：
- 模型有了一张"地图"，不会在执行中迷失方向
- 减少无效的工具调用和回溯
- 执行计划本身只占 ~100 tokens，成本极低

**触发条件**：消息包含"然后、接着、再、同时"等多意图关键词时才生成计划，简单消息跳过。

---

## 13. 一个完整的上下文组装过程（本项目实战）

现在把所有策略串起来，看本项目 `_prepare_context()` 方法一镜到底做了什么：

```python
async def _prepare_context(self, request):
    """每次用户发消息，组装上下文的全过程"""

    # ═══════════════════════════════════════════════
    # STEP 1: 意图路由 → 缩减工具列表
    # ═══════════════════════════════════════════════
    intent_label, candidate_tools = await intent_router.route(request.message)
    # "shopping" → 只给 LLM 7 个购物工具而非全部 40 个
    tools = ToolRegistry.list_tools(candidate_tools)
    # 工具定义从 8000+ tokens → ~1400 tokens

    # ═══════════════════════════════════════════════
    # STEP 2: 记忆注入 → 跨会话上下文
    # ═══════════════════════════════════════════════
    if user_id not in self._memory_injected:
        # 该用户首次出现 → 从向量库检索历史记忆
        memory_context = await mem.retrieve_user_summary(user_id)
        # memory_context = "用户是3口之家，偏好川菜，有花生过敏..."
        self._memory_injected.add(user_id)  # 标记，本次会话不再重复注入

    # ═══════════════════════════════════════════════
    # STEP 3: 构建 System Prompt
    # ═══════════════════════════════════════════════
    full_prompt = self._build_full_prompt(
        user_id,
        profile={"name": "张三", "family_size": 3, "allergies": ["花生"]},
        memory_context="上次对话：用户偏好蒜蓉做法，冰箱有临期菠菜..."
    )
    # 拼接结果：
    #   基础 System Prompt (你是家务AI管家...)
    #   + 用户档案 (张三 | 3口人 | 忌花生)
    #   + 当前时间 (2026-07-30 14:30)
    #   + 记忆上下文 (上次聊过菠菜...)
    #   + 行为约束 (优先调工具，口语化回复...)

    # ═══════════════════════════════════════════════
    # STEP 4: Plan-and-Execute → 复杂任务分解
    # ═══════════════════════════════════════════════
    plan_steps = await self._generate_plan(request.message)
    if plan_steps:
        full_prompt += "\n## 执行计划\n  1. 步骤A\n  2. 步骤B\n..."

    # ═══════════════════════════════════════════════
    # STEP 5: 构建 Messages 数组
    # ═══════════════════════════════════════════════
    messages = [{"role": "system", "content": full_prompt}]  # 第一条

    # ═══════════════════════════════════════════════
    # STEP 6: 滑动窗口 + 摘要压缩 → 对话历史
    # ═══════════════════════════════════════════════
    history = await mem.get_history(session_id)

    if len(history) > 5:              # 超过 5 轮
        old = history[:-5]            # 截取旧的部分
        summary = await summarize(old) # LLM 压缩
        messages.append({"role": "system", "content": f"[历史摘要] {summary}"})
        # 旧 15 轮对话 (10K tokens) → 摘要 (50 tokens)

    for h in history[-5:]:            # 最近 5 轮完整保留
        messages.append({"role": h.role, "content": h.content})

    # ═══════════════════════════════════════════════
    # STEP 7: 追加当前消息
    # ═══════════════════════════════════════════════
    messages.append({"role": "user", "content": request.message})

    # ═══════════════════════════════════════════════
    # 最终 messages 结构:
    # ═══════════════════════════════════════════════
    # [0] system:  完整 System Prompt
    #               → 角色 + 档案 + 时间 + 记忆 + 规则 + 执行计划
    #               ≈ 1500 tokens
    # [1] system:  [历史摘要] 之前聊过冰箱库存、菜谱推荐...
    #               ≈ 50 tokens
    # [2] user:    最近对话 - 第 26 轮问题
    # [3] assistant: 最近对话 - 第 26 轮回答
    # [4] user:    最近对话 - 第 27 轮问题
    # ...
    # [10] user:   当前消息 "菠菜能做什么菜？"
    #               ≈ 3000 tokens 总计

    return {"messages": messages, "tools": tools, ...}
```

### 最终效果

```
没有上下文管理:
  System (1K) + 40 工具定义 (8K) + 30 轮完整对话 (20K) +
  工具返回结果 (5K) + 当前消息
  = 34K tokens → 成本 0.034 元/次 → 一天 1000 次 = 34 元

有上下文管理:
  System (1.5K) + 7 工具定义 (1.4K) + 摘要 (0.05K) +
  最近 5 轮 (1K) + 工具结果 (3K) + 当前消息
  = 7K tokens → 成本 0.007 元/次 → 一天 1000 次 = 7 元

节省 80%！同时回答质量没有下降（因为核心信息都在）。
```

---

## 总结：上下文管理清单

| 步骤 | 做了什么 | 节省/效果 |
|------|---------|----------|
| 意图路由 | 40 工具 → 7 工具 | 节省 82% 工具定义 token |
| 记忆注入 | 跨会话信息只注入一次 | 首次对话多 200 token，之后 0 |
| 动态 System Prompt | 拼接用户档案 + 时间 + 规则 | 一次性，成本固定 |
| Plan-and-Execute | 复杂任务预分解 | 减少无效工具调用和回溯 |
| 滑动窗口 | 只保留最近 5 轮 | 对话历史从 20K → 1K |
| 摘要压缩 | 旧对话压缩为 50 字摘要 | 旧信息 10K → 50 token |

> **上下文管理的本质**：不是"能塞多少塞多少"，而是"用最少的 token，让模型获得回答所需的最关键信息"。

---

## 14. 进阶技术 — 上下文管理的更多武器

你问"是不是就这么多了"——远远不止。前面讲的五种策略是基础款，下面这些是业界更进阶的做法。

### 14.1 技术全景图

```
上下文管理技术

├─ 📏 长度控制（解决上下文太长）
│   ├─ 滑动窗口 ────────── 已讲
│   ├─ 摘要压缩 ────────── 已讲
│   ├─ Token 精确裁剪 ──── 按实际 token 数截断，而非轮数
│   └─ 分层摘要 ────────── 多级压缩（消息→会话→用户全史）
│
├─ 🧠 记忆增强（解决跨会话遗忘）
│   ├─ 向量记忆注入 ────── 已讲
│   ├─ MemGPT 虚拟内存 ─── 把上下文当操作系统内存管理
│   ├─ 反思记忆 ────────── Agent 定期反思并保存"心得"
│   └─ 实体记忆 ────────── 按"用户/食材/家电"等实体组织记忆
│
├─ 🎯 注意力优化（解决"中间信息被忽略"）
│   ├─ 意图路由 ────────── 已讲
│   ├─ 结构化上下文 ────── 用 XML/JSON 标签标记重要度
│   ├─ 位置编排 ────────── 把最重要的信息放开头和结尾
│   └─ Prompt Caching ──── 缓存不变部分，节省成本
│
├─ 🔄 动态调节（解决不同场景需要不同上下文）
│   ├─ Plan-and-Execute ─── 已讲
│   ├─ 渐进披露 ────────── 先用最小上下文，不够再追加
│   ├─ 反思回溯 ────────── Agent 执行中自我检查进度
│   └─ 自适应窗口 ──────── 根据任务复杂度动态调整保留轮数
│
└─ 🔗 外部增强（从外部引入上下文）
    ├─ RAG 检索增强 ────── 从知识库检索相关文档
    ├─ Web 搜索兜底 ────── 知识库没有时搜互联网
    └─ 多模态上下文 ────── 图片、音频也作为上下文
```

### 14.2 Token 精确裁剪

滑动窗口按"轮数"截断是粗粒度的。精确的做法是按 **token 数**截断：

```python
# ❌ 粗粒度 — 保留最近 5 轮，但每轮长度不同
if len(history) > 5:
    history = history[-5:]  # 5 轮可能是 3K 也可能是 20K tokens

# ✅ 精确裁剪 — 保留最近 4000 tokens
def trim_by_tokens(messages, max_tokens=4000):
    total = 0
    kept = []
    for msg in reversed(messages):    # 从最新往前数
        tokens = count_tokens(msg.content)
        if total + tokens > max_tokens:
            break
        kept.insert(0, msg)
        total += tokens
    return kept
```

**为什么不用？** 本项目对话较短（家务场景），按轮数够用。当你的场景变成"代码审查"或"长文档问答"时就需要这个。

### 14.3 分层摘要

摘要不只能做一次。可以多级压缩：

```
原始对话（30轮，50K tokens）
        │
        ▼ 一级摘要（每 10 轮 → 一段摘要）
  摘要1: 用户讨论了冰箱库存...
  摘要2: 用户规划了本周菜谱...
  摘要3: 用户预约了家电维保...
        │
        ▼ 二级摘要（3 段 → 1 段）
  "本周用户管理了冰箱库存，规划了5天菜谱，
   预约了空调维保，总消费预算约500元。"
        │
        ▼ 用户画像（所有二级摘要 → 固定字段）
  {
    "偏好口味": ["川菜", "粤菜"],
    "常用食材": ["番茄", "鸡蛋", "鸡胸肉"],
    "月均消费": 3000,
    "家电关注": ["空调维保", "错峰省电"]
  }
```

本项目只做了一级摘要（旧对话→一句话）。分层摘要适合需要长期用户画像的大项目。

### 14.4 MemGPT / Letta — 把上下文当虚拟内存

这是上下文管理领域最激进的思路，来自 MemGPT 论文（2023）：

```
操作系统的虚拟内存:           MemGPT 的"虚拟上下文":
┌──────────────┐            ┌──────────────────────┐
│ 物理内存 (RAM)│            │ 上下文窗口 (Context)   │
│ 容量: 16GB    │            │ 容量: 128K tokens     │
│ 速度: 快      │            │ 速度: 快              │
├──────────────┤            ├──────────────────────┤
│ 虚拟内存 (SSD)│            │ 外部存储 (Vector DB)   │
│ 容量: 512GB   │            │ 容量: 数百万 tokens    │
│ 速度: 慢      │            │ 速度: 慢（需检索）     │
└──────────────┘            └──────────────────────┘

工作原理:
1. 上下文窗口 ≈ RAM → 放当前正在用的信息
2. 向量数据库 ≈ SSD → 放所有历史信息
3. 当需要的信息不在上下文里 → "缺页中断" → 从向量库检索加载
4. 上下文快满了 → "页面换出" → 把不重要的信息写回向量库
```

LLM 能主动调用函数来"读写记忆"，就像一个微型的操作系统。

**项目当前做到的程度**：有向量记忆（SSD）+ 上下文窗口（RAM），但没有"自动换页"——记忆是在会话开始时一次性注入的，不会在对话中动态加载/卸载。如果要做非常长的持续对话（比如客服系统，一个用户聊了几百轮），就需要 MemGPT 思路。

### 14.5 结构化上下文 — 用标签帮 LLM 理解信息优先级

LLM 对纯文本的不同部分是一视同仁的。用 XML/JSON 标签标记信息的重要度，可以帮助模型更好地区分：

```python
# ❌ 扁平结构 — 模型可能忽略重要信息
system_prompt = """
用户档案: 张三，3口人，忌花生，偏好川菜。
上次对话: 用户问了菠菜做法。
历史摘要: 讨论了冰箱库存。
规则: 优先调工具，口语化回复。
"""

# ✅ 结构化标记 — 模型能区分信息层次
system_prompt = """
<role>你是家务AI管家</role>

<critical>
  <allergies>花生过敏（致命）</allergies>
  <budget>月度预算 3000 元</budget>
</critical>

<context>
  <user_profile>张三，3口人，偏好川菜</user_profile>
  <recent_memory>上次讨论了菠菜做法</recent_memory>
  <session_summary>本周已规划 3 天菜谱</session_summary>
</context>

<rules>
  <rule priority="high">优先调工具再回答</rule>
  <rule priority="medium">口语化中文回复</rule>
</rules>
"""
```

Anthropic 的 Claude 官方推荐这种写法。本项目没用是因为 DeepSeek 对这种格式没有特别优化，但如果你用 Claude 或者未来切到更强的模型，这是标配做法。

### 14.6 Prompt Caching — 缓存不变的上下文，省成本

你每次请求都重复发送的 System Prompt 和工具定义，大部分是不变的。Prompt Caching 就是把这些"每次都一样"的部分缓存起来：

```
第 1 次请求:
  System Prompt (1.5K tokens) ← 首次发送，全价
  工具定义 (2K tokens)        ← 首次发送，全价
  当前消息 (0.5K tokens)
  总成本: 4K × 1 元/百万 = 0.004 元

第 2 ~ N 次请求:
  System Prompt (1.5K) ← 缓存命中，1/10 价格
  工具定义 (2K)        ← 缓存命中，1/10 价格
  当前消息 (0.5K)
  总成本: 0.5K × 全价 + 3.5K × 0.1 = 0.00085 元  （节省 79%）
```

| 平台 | 缓存机制 |
|------|---------|
| Anthropic Claude | 原生 Prompt Caching，命中后价格打 1 折 |
| OpenAI | Automatic Caching（自动），命中也打折 |
| DeepSeek | Context Caching，需显式标记缓存前缀 |

本项目用的 DeepSeek，支持 Context Caching 但代码里没用——因为当前对话长度还不算长，缓存收益有限。当你的 System Prompt 达到 5K+ tokens 时就该开了。

### 14.7 位置编排 — 把最重要的放对位置

LLM 有一个经典的"Lost in the Middle"现象：

```
上下文阅读注意力分布:
  ████████████  开头  ← 注意力最高
  ██████        中段  ← 注意力最低！
  ████████████  结尾  ← 注意力最高
```

所以上下文编排有一个黄金法则：

```python
# 最重要的信息 → 放开头或结尾
# 次要的背景信息 → 放中间

messages = [
    {"role": "system", "content": (
        f"你是家务AI管家。\n"
        f"⚠️ 重要：用户对花生致命过敏，任何含花生的菜谱都不能推荐。\n"  # ← 开头
        f"{context_that_can_be_in_middle}"                              # ← 中间
        f"请根据以上信息回答。记住：用户忌花生。"                        # ← 结尾重申
    )},
]
```

### 14.8 渐进披露 Progressive Disclosure

不是一次性把所有上下文塞给 LLM，而是分两步：

```python
# 第一步：先给最小上下文
minimal_context = [system_prompt, user_message]
first_response = await llm.chat(minimal_context)

# 第二步：如果 LLM 表示"信息不足"或调了记忆工具
if first_response.indicates_need_for_context():
    additional_context = await retrieve_memories(user_message)
    messages.append({"role": "tool", "content": additional_context})
    final_response = await llm.chat(messages)
```

好处：
- 简单问题（"你好"）只用 1.5K token，而不是 7K
- 需要时才加载记忆，按需付费

### 14.9 反思记忆 Reflection Memory

让 Agent 在完成任务后**自我反思**，把"心得"存进记忆：

```python
async def reflect_and_save(self, dialog_history, user_id):
    """完成一轮对话后，自我反思"""
    reflection_prompt = """
    请反思刚才的对话：
    1. 用户暴露了哪些新偏好？
    2. 哪些回答策略效果好？
    3. 下次遇到类似问题应该怎么做？
    只输出最关键的 1-2 条 insight。
    """
    insights = await self.client.chat.completions.create(
        model=settings.openai_model,
        messages=[...],
        max_tokens=100,
    )
    # 存入长期记忆
    await memory.save_reflection(user_id, insights)
```

这样 Agent 不仅仅是"记住了对话内容"，而是"从对话中学到了东西"。本项目有偏好自动提取（`_schedule_preference_extraction`），但更偏结构化；反思记忆是更自然的形式。

---

### 14.10 你现在的位置 vs 还缺什么

```
上下文管理成熟度阶梯:

Level 0:  没有上下文管理 — 每次都是新对话
Level 1:  滑动窗口 — 保留最近 N 轮              ← 
Level 2:  + 摘要压缩 — 旧对话不丢                ← 你现在在这里
Level 3:  + 记忆注入 — 跨会话感知                ← 
Level 4:  + 意图路由 — 减少无关工具              ←
Level 5:  + Plan-and-Execute — 复杂任务分解      ←
─────────────────────────────────────────────
Level 6:  + Token 精确裁剪 — 按 token 而非轮数
Level 7:  + 结构化上下文 — XML 标签标记优先级
Level 8:  + Prompt Caching — 省成本
Level 9:  + 渐进披露 — 按需加载
Level 10: + MemGPT 虚拟内存 — 自动换页
Level 11: + 反思记忆 — 从对话中学习
```

你的项目处于 **Level 5**，对一个家务 AI 管家来说已经足够。Level 6+ 是当你遇到这些场景时才需要的：

| 触发场景 | 需要升级的技术 |
|---------|-------------|
| 用户单次会话超过 50 轮 | Token 精确裁剪 + 分层摘要 |
| 月成本超过预算 | Prompt Caching |
| 用户反馈"AI 记不住重要信息" | 结构化上下文 + 位置编排 |
| 需要长期学习用户习惯 | 反思记忆 |
| 需要极长的持续性对话（客服/陪伴） | MemGPT 虚拟内存 |

> **一句话**：上下文管理没有银弹，只有根据场景选择合适组合的工程判断。你现在用的五种策略，对于一个家庭 AI 管家来说，够用且恰到好处。
