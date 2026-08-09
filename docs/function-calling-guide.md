# 🔧 Function Calling（工具调用）完全指南

> LLM 本身只能输出文字。Function Calling 就是给它接上手和脚，让它能操作真实世界。

---

## 目录

1. [Function Calling 是什么？](#1-function-calling-是什么)
2. [怎么定义工具？JSON Schema](#2-怎么定义工具json-schema)
3. [一次完整的调用周期](#3-一次完整的调用周期)
4. [并行工具调用](#4-并行工具调用)
5. [工具结果怎么返回给 LLM](#5-工具结果怎么返回给-llm)
6. [错误处理三板斧](#6-错误处理三板斧)
7. [最佳实践](#7-最佳实践)
8. [高级模式](#8-高级模式)
9. [本项目实战解析](#9-本项目实战解析)

---

## 1. Function Calling 是什么？

### 一句话

**Function Calling 是 LLM 的"动手能力"——模型不说"你应该去查冰箱库存"，而是直接帮你查了。**

### 没有 Function Calling

```
用户: "冰箱里有什么？"

LLM: "你可以打开冰箱门，看看里面有什么食材..."  
     ← 只能给文字建议，什么也做不了
```

### 有 Function Calling

```
用户: "冰箱里有什么？"

LLM 输出: 调用工具 get_fridge_inventory(user_id="user_001")

你的代码执行: get_fridge_inventory("user_001")
  → 返回: [{"name": "菠菜", "quantity": 0.5}, {"name": "鸡蛋", "quantity": 10}]

LLM 看到结果: "您冰箱里有菠菜0.5斤、鸡蛋10个。菠菜快过期了，建议尽快食用。"
     ← 基于真实数据回答，不是瞎编的
```

### 本质：LLM 学会了"按按钮"

```
传统 LLM:
  用户输入 → LLM → 文字输出

Function Calling LLM:
  用户输入 → LLM → 两种可能的输出:
                     ├─ 纯文字（不需要工具时）
                     └─ Function Call（需要工具时）
                              ↓
                        你的代码执行这个函数
                              ↓
                        把结果传回给 LLM
                              ↓
                        LLM 基于结果生成最终回复
```

---

## 2. 怎么定义工具？JSON Schema

### 2.1 基本格式

```json
{
  "type": "function",
  "function": {
    "name": "get_fridge_inventory",
    "description": "查看冰箱里有哪些食材，包括数量、过期日期、存放位置",
    "parameters": {
      "type": "object",
      "properties": {
        "user_id": {
          "type": "string",
          "description": "用户ID"
        }
      },
      "required": ["user_id"]
    }
  }
}
```

### 2.2 JSON Schema 参数类型

```json
{
  "parameters": {
    "type": "object",
    "properties": {

      // 简单类型
      "query": {
        "type": "string",
        "description": "搜索关键词"
      },

      "limit": {
        "type": "integer",
        "description": "返回结果数",
        "default": 5
      },

      "price": {
        "type": "number",
        "description": "最高价格"
      },

      "is_urgent": {
        "type": "boolean",
        "description": "是否紧急"
      },

      // 枚举
      "meal_type": {
        "type": "string",
        "enum": ["breakfast", "lunch", "dinner", "snack"],
        "description": "餐食类型"
      },

      // 数组
      "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "筛选标签",
        "maxItems": 10
      },

      // 对象（嵌套）
      "meal_plan": {
        "type": "object",
        "properties": {
          "start_date": {"type": "string"},
          "days": {"type": "integer"}
        },
        "description": "菜谱计划参数"
      }
    },
    "required": ["query"]   // 必填字段
  }
}
```

### 2.3 写好 Tool Description 的艺术

**description 决定了 LLM 什么时候用它**：

```python
# ❌ 糟糕的 description — LLM 不知道该不该用
ToolRegistry.register(
    "search_things",
    func,
    "搜索东西",      # ← 太模糊！
    {"properties": {"q": {"type": "string"}}}
)

# ✅ 好的 description — LLM 清楚知道何时使用
ToolRegistry.register(
    "search_recipes",
    func,
    "搜索菜谱，可按菜系/类型/时间/标签筛选",   # ← 明确了功能
    {
        "properties": {
            "query": {"type": "string", "description": "菜名或关键词，如'红烧肉'"},
            "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner"],
                          "description": "餐食类型"},
            "cuisine": {"type": "string", "description": "菜系，如'川菜'、'粤菜'"},
            "max_cooking_time": {"type": "integer", "description": "最长烹饪时间（分钟）"},
        }
    }
)
```

**写好 description 的规则**：

```
1. 说清楚工具做什么（不是怎么实现）
2. 说明什么时候用它（触发条件）
3. 每个参数说明含义 + 示例值
4. 如果有互斥/关联参数关系，写清楚
```

---

## 3. 一次完整的调用周期

### 3.1 请求：把工具定义发给 LLM

```python
import openai

client = openai.AsyncOpenAI(api_key="xxx", base_url="https://api.deepseek.com/v1")

response = await client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "你是家务AI管家。"},
        {"role": "user", "content": "冰箱里有什么？"},
    ],
    tools=[                              # ← 工具定义
        {
            "type": "function",
            "function": {
                "name": "get_fridge_inventory",
                "description": "查看冰箱里有哪些食材",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"}
                    },
                    "required": ["user_id"]
                }
            }
        }
    ],
    temperature=0.7,
)
```

### 3.2 响应：判断 LLM 是不是要调工具

```python
choice = response.choices[0]
message = choice.message

if message.tool_calls:
    # LLM 决定调工具！
    for tool_call in message.tool_calls:
        tool_name = tool_call.function.name        # "get_fridge_inventory"
        tool_args = json.loads(tool_call.function.arguments)  # {"user_id": "user_001"}
        tool_call_id = tool_call.id                 # "call_abc123"

        # 执行工具
        result = await get_fridge_inventory(**tool_args)
        # → [{"name": "菠菜", "quantity": 0.5}, ...]

else:
    # LLM 直接回答了（不需要调工具）
    final_answer = message.content
```

### 3.3 把结果传回 LLM

```python
# ① 先把 assistant 的 tool_calls 消息加入对话
messages.append({
    "role": "assistant",
    "content": None,              # 调工具时 content 是 None
    "tool_calls": [
        {
            "id": tool_call.id,           # ← 必须和 tool 消息的 id 匹配！
            "type": "function",
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            }
        }
    ]
})

# ② 再把工具结果加入对话
messages.append({
    "role": "tool",                 # ← 角色是 "tool"
    "tool_call_id": tool_call.id,   # ← 跟上面 assistant 消息里的 id 对应
    "content": json.dumps(result),  # ← 工具返回值，必须是字符串
})

# ③ 再次调用 LLM，让它基于结果生成最终回答
final_response = await client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,   # ← 现在包含了完整的对话 + 工具调用结果
    tools=tools,
)
# 这次 LLM 会输出: "您冰箱里有菠菜0.5斤、鸡蛋10个..."
```

### 3.4 完整流程图

```
Step 1: 用户: "冰箱里有什么？"
  messages = [system_prompt, user_message]
  tools = [get_fridge_inventory, ...]
  → LLM 输出: tool_calls = [{name: "get_fridge_inventory", args: {user_id: "u1"}}]
    content = None  (调工具时不输出文字)

Step 2: 执行工具
  result = get_fridge_inventory(user_id="u1")
  → [{"name": "菠菜", "quantity": 0.5}, {"name": "鸡蛋", "quantity": 10}]

Step 3: 结果放入 messages
  messages = [
    system_prompt,
    user_message,
    {"role": "assistant", "tool_calls": [...]},     ← assistant 说"我要调这个工具"
    {"role": "tool", "content": json.dumps(result)}, ← 工具返回结果
  ]

Step 4: 再次调 LLM
  messages = [system_prompt, user_message, assistant(tool_call), tool(result)]
  tools = [get_fridge_inventory, ...]
  → LLM 输出: content = "您冰箱里有菠菜0.5斤（明天过期）、鸡蛋10个..."
    tool_calls = None  (不调工具了，直接回答)
```

---

## 4. 并行工具调用

### 4.1 LLM 一次可以决定调多个工具

```python
# LLM 收到: "检查冰箱库存，同时看看空调状态"
# LLM 输出多个 tool_calls:
message.tool_calls = [
    {
        "id": "call_1",
        "function": {"name": "get_fridge_inventory", "arguments": '{"user_id":"u1"}'}
    },
    {
        "id": "call_2",
        "function": {"name": "get_appliance_status", "arguments": '{"user_id":"u1"}'}
    },
]
```

### 4.2 并行执行（用 asyncio.gather）

```python
# ❌ 串行 — 慢
for tc in message.tool_calls:
    result = await execute_tool(tc)  # 等一个完了再下一个

# ✅ 并行 — 快
results = await asyncio.gather(
    *[execute_tool(tc) for tc in message.tool_calls],
    return_exceptions=True,  # 一个失败不拖累其他
)

# 总时间 = max(每个工具的时间)，不是 sum(每个工具的时间)
```

### 4.3 并行调用后怎么回传

```python
# 一个 assistant 消息可以包含多个 tool_calls
messages.append({
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "fridge", "arguments": "..."}},
        {"id": "call_2", "type": "function", "function": {"name": "appliance", "arguments": "..."}},
    ]
})

# 每个 tool_call 对应一个 tool 消息
for tc, result in zip(message.tool_calls, results):
    messages.append({
        "role": "tool",
        "tool_call_id": tc.id,      # ← 必须一一对应
        "content": json.dumps(result),
    })

# 最后再调一次 LLM，这次它会同时看到两个工具的结果
```

---

## 5. 工具结果怎么返回给 LLM

### 5.1 结果必须序列化为字符串

```python
# ❌ 直接传对象
messages.append({
    "role": "tool",
    "tool_call_id": tc.id,
    "content": {"name": "菠菜", "price": 3.5},   # ← dict！API 会报错
})

# ✅ 序列化为 JSON 字符串
messages.append({
    "role": "tool",
    "tool_call_id": tc.id,
    "content": json.dumps({"name": "菠菜", "price": 3.5}, ensure_ascii=False),
})
```

### 5.2 结果太长怎么办

```python
# JSON 结果可能有几千字 — 全塞给 LLM 浪费 token

result = await search_all_products("番茄")
# → [{"name": "番茄", "price": 3.5}, {...}, ...共 50 条]

# 截断
result_str = json.dumps(result[:5], ensure_ascii=False)  # 只取前 5 条
# 或摘要化
result_str = f"找到 {len(result)} 个结果。最低价: {min_price}元, 最高价: {max_price}元"
```

### 5.3 错误结果也要格式化

```python
try:
    result = await tool_func(**args)
    result_str = json.dumps(result, ensure_ascii=False)
except Exception as e:
    # 错误也要返回，让 LLM 知道"这个操作失败了"
    result_str = json.dumps({"error": str(e), "tool": tool_name}, ensure_ascii=False)
    # LLM 看到 {"error": "..."} 后会说 "抱歉，查询失败了，请稍后再试"
```

---

## 6. 错误处理三板斧

### 6.1 类型强转 — LLM 的输出不可信

```python
# LLM 可能传: {"limit": "5"}  ← 字符串
# LLM 可能传: {"limit": 5.0}  ← 浮点数
# 你期望:     {"limit": 5}     ← 整数

for key, prop_info in schema["properties"].items():
    val = arguments.get(key)
    expected = prop_info.get("type")

    if expected == "integer" and not isinstance(val, int):
        val = int(val)           # "5" → 5, 5.0 → 5
    elif expected == "number":
        val = float(val)
    elif expected == "boolean" and isinstance(val, str):
        val = val.lower() in ("true", "1", "yes")
```

### 6.2 缺失参数 + 边界校验

```python
# ① 缺失必填参数
required = set(schema.get("required", []))
for key in required:
    if key not in arguments:
        return {"error": f"缺少必需参数: {key}"}

# ② 边界校验
if quantity <= 0:
    return {"error": f"数量必须大于0"}
if expiry_days < 0:
    return {"error": f"过期天数不能为负数"}
if not name or not name.strip():
    return {"error": "名称不能为空"}
```

### 6.3 自动修复 — 失败了再试一次

```python
async def _auto_fix_and_retry(self, tool_name, args, error_msg, user_id):
    """LLM 分析错误原因，生成修复后的参数，重试一次"""

    # ① 让 LLM 分析为什么失败
    resp = await self.client.chat.completions.create(
        model=settings.openai_model,
        messages=[{
            "role": "system",
            "content": "你是参数修复助手。分析错误原因，输出修复后的 JSON 参数。只输出 JSON。"
        }, {
            "role": "user",
            "content": f"工具名: {tool_name}\n原参数: {args}\n错误信息: {error_msg}"
        }],
        temperature=0,
        max_tokens=300,
    )

    # ② 解析修复后的参数
    try:
        content = resp.choices[0].message.content
        if "```" in content:                    # 去掉 Markdown 包裹
            content = content.split("```")[1].replace("json", "")
        fixed = json.loads(content.strip())
    except json.JSONDecodeError:
        return None, error_msg

    # ③ 用修复后的参数重试
    if fixed == args or fixed.get("unfixable"):
        return None, error_msg   # 修不了，放弃

    result = await self._call_tool(tool_name, fixed, user_id,
                                    max_retries=1, timeout_seconds=15.0)
    return fixed, result
```

---

## 7. 最佳实践

### 7.1 工具数量：少即是多

```
❌ 给 LLM 100 个工具 → 它不知道该选哪个，容易选错
✅ 按意图只给 5-10 个相关工具 → 准确率高得多

你项目的做法:
  用户说 "番茄多少钱" → 意图路由 → 只给 7 个购物工具（不是全部 40 个）
```

### 7.2 工具粒度：一个工具只做一件事

```
❌ do_everything(action, target, params...)  ← 万能工具，LLM 不会用
✅ get_fridge_inventory()                    ← 一个工具一个职责
✅ add_fridge_item()                          ← LLM 明确知道何时调用
✅ search_recipes()                           ← 清晰的功能边界
```

### 7.3 结果格式：适合 LLM 理解

```python
# ❌ 返回原始数据库对象
return db_result   # → <FridgeItem object at 0x7f...>  ← LLM 看不懂

# ✅ 返回简洁的 dict
return {
    "items": [
        {"name": "菠菜", "quantity": 0.5, "expiry": "2026-07-30"},
        {"name": "鸡蛋", "quantity": 10}
    ],
    "total": 2
}
```

### 7.4 安全护栏：危险操作要确认

```python
# 不同工具标记不同危险等级
danger_level:
  "safe"       → 直接执行（查库存、搜菜谱）
  "caution"    → 可执行但记录日志（发通知）
  "dangerous"  → 必须用户确认！（控制家电、设防）

# 危险操作拦截
if danger_level == "dangerous" and not confirmed:
    return {"requires_confirmation": True,
            "message": "即将关闭全部门窗并设防，请确认。"}
```

### 7.5 注入上下文参数

```python
# LLM 可能不知道自己的 user_id — 你帮它注入
if "user_id" not in arguments and user_id:
    arguments["user_id"] = user_id  # ← 自动补上，LLM 不需要关心
```

---

## 8. 高级模式

### 8.1 多轮工具调用（ReAct 循环）

```python
max_iterations = 10

for iteration in range(max_iterations):
    response = await llm.chat(messages, tools)

    if response.tool_calls:
        # 调工具
        results = await execute_tools(response.tool_calls)
        # 追加到 messages
        messages.append(assistant_msg(response.tool_calls))
        for tc, result in zip(response.tool_calls, results):
            messages.append(tool_msg(tc.id, result))
        continue  # ← 继续循环，让 LLM 看到结果后再决定下一步

    else:
        # 没有工具调用了 → 最终答案
        return response.content
```

### 8.2 死循环检测

```python
last_tool_signature = ""
repeat_count = 0

for iteration in range(max_iterations):
    response = await llm.chat(messages, tools)

    if response.tool_calls:
        # 检测是否和上一轮调了完全相同的工具
        this_sig = "|".join(f"{tc.function.name}:{tc.function.arguments[:120]}"
                            for tc in response.tool_calls)

        if this_sig == last_tool_signature:
            repeat_count += 1
            if repeat_count >= 3:   # 相同调用重复了 3 次
                return "抱歉，处理遇到困难。请换个方式描述需求。"
        else:
            repeat_count = 0
        last_tool_signature = this_sig
        # ... 继续执行工具
```

### 8.3 Strict Mode（严格模式）

```python
# OpenAI 的 strict 模式强制 LLM 严格遵守 schema
{
    "type": "function",
    "function": {
        "name": "search",
        "strict": True,     # ← 启用严格模式
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"}
            },
            "required": ["query", "limit"],
            "additionalProperties": False   # 不允许额外参数
        }
    }
}
```

---

## 9. 本项目实战解析

### 9.1 你的工具注册体系

```python
# 全局注册表 — 所有工具都注册到这里
class ToolRegistry:
    _tools: dict[str, dict] = {}   # {工具名: {function, description, parameters, danger_level}}

    @classmethod
    def register(cls, name, func, description, parameters, danger_level="safe"):
        cls._tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
            "danger_level": danger_level,   # ← 你项目的特色
        }

    @classmethod
    def list_tools(cls, names=None) -> list[dict]:
        """生成 OpenAI 兼容的工具定义列表"""
        result = []
        for name, info in cls._tools.items():
            if names is None or name in names:
                result.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": info["description"],
                        "parameters": info["parameters"],
                    }
                })
        return result
```

### 9.2 你的三个危险等级

```python
# safe — 直接执行
ToolRegistry.register("get_fridge_inventory", func,
    "查看冰箱里有哪些食材",
    {"type": "object", "properties": {"user_id": {"type": "string"}}},
    danger_level="safe")

# caution — 可执行但需要记录
ToolRegistry.register("send_notification", func,
    "向用户发送通知",
    {"type": "object", ...},
    danger_level="caution")

# dangerous — 必须用户确认！
ToolRegistry.register("set_away_mode", func,
    "设置离家布防模式：关门窗、设防、关灯",
    {"type": "object", ...},
    danger_level="dangerous")
```

### 9.3 你的 ReAct 循环中的工具调用

```python
async def run(self, request):
    # Step 0: 准备上下文（意图路由、记忆注入、对话历史）
    ctx = await self._prepare_context(request)
    messages = ctx["messages"]
    tools = ToolRegistry.list_tools(ctx["routed_tools"])  # 只给相关工具

    for iteration in range(self.max_iterations):
        # Step 1: 调 LLM
        resp = await self.client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tools,
            temperature=settings.llm_temperature,
        )

        msg = resp.choices[0].message

        # Step 2: 判断 LLM 是否调用了工具
        if msg.tool_calls:
            # 死循环检测
            this_sig = "|".join(
                f"{tc.function.name}:{tc.function.arguments[:120]}"
                for tc in msg.tool_calls
            )
            if this_sig == last_tool_sig:
                repeat_count += 1
                if repeat_count >= 3:
                    return AgentResponse(response="抱歉，处理遇到困难...")
            else:
                repeat_count = 0
            last_tool_sig = this_sig

            # 并行执行所有工具！
            results = await asyncio.gather(
                *[self._call_tool(tc.function.name,
                                   json.loads(tc.function.arguments),
                                   user_id)
                  for tc in msg.tool_calls],
                return_exceptions=True,
            )

            # 追加 assistant(tool_calls) + tool(result) 到 messages
            messages.append(assistant_msg)
            for tc, result in zip(msg.tool_calls, results):
                # 安全护栏检测
                if "requires_confirmation" in result:
                    return AgentResponse(requires_confirmation=True, ...)

                # 自动修复检测
                if "error" in result:
                    fixed_args, retry_result = await auto_fix(...)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            continue  # ← 继续循环

        # Step 3: 纯文本 → 最终答案
        else:
            return AgentResponse(response=msg.content)
```

### 9.4 你的 call_tool 核心逻辑

```python
async def _call_tool(self, name, arguments, user_id,
                     max_retries=3, timeout_seconds=30.0,
                     confirmed_dangerous=False):
    """调用一个工具 — 带安全护栏、参数校验、重试、超时"""

    # ① 安全护栏
    if ToolRegistry.get_danger_level(name) == "dangerous" and not confirmed_dangerous:
        return json.dumps({"requires_confirmation": True, ...})

    # ② 自动注入 user_id
    if "user_id" not in arguments:
        arguments["user_id"] = user_id

    # ③ 类型强转（string→int, string→float, string→bool）
    for key, prop in schema["properties"].items():
        if key in arguments:
            val = arguments[key]
            if prop["type"] == "integer" and not isinstance(val, int):
                val = int(val)
            ...

    # ④ 重试循环（最多 3 次，带退避）
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                tool_func(**arguments),
                timeout=timeout_seconds,
            )
            return json.dumps(result, ensure_ascii=False)
        except asyncio.TimeoutError:
            await asyncio.sleep(0.5 * (attempt + 1))   # 退避
            continue
        except Exception as e:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue

    return json.dumps({"error": "工具调用失败"}, ensure_ascii=False)
```

---

## 核心总结

```
Function Calling 的四个阶段:

  ① 定义工具     JSON Schema 告诉 LLM "你能做什么"
  ② LLM 决策     LLM 基于问题选择工具和参数
  ③ 执行工具     你的代码实际运行函数
  ④ 回传结果     tool_result → messages → LLM → 最终回复

关键原则:
  - description 写清楚 → LLM 知道何时调用
  - 参数要校验     → LLM 的输出不可信
  - 错误要格式化   → 让 LLM 知道"出错了"而不是静默失败
  - 能并行就并行   → asyncio.gather 省时间
  - 危险操作要确认 → safety guard 人是最后防线
```

> **Function Calling 的本质**：不是让 LLM 变聪明，是给 LLM 装上手脚。LLM 负责"想"，你的代码负责"做"。

---

## 10. 2024-2025 最新技术

### 10.1 Structured Outputs — 强制 JSON Schema（OpenAI 2024.8）

这是 2024 年最重要的更新。之前的 Function Calling 有个顽疾：**LLM 说好了返回 JSON，但偶尔会多打个逗号、少个引号**。

```python
# 旧方式：LLM "尽量"返回合法 JSON → 可能失败
# 新方式：Structured Outputs → 100% 保证返回合法 JSON

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "列出3种蔬菜"}],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "vegetable_list",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "price": {"type": "number"},
                                "in_stock": {"type": "boolean"},
                            },
                            "required": ["name", "price", "in_stock"],
                            "additionalProperties": False,  # ← 不允许额外字段
                        }
                    }
                },
                "required": ["items"],
                "additionalProperties": False,
            }
        }
    },
)
# 返回一定是合法 JSON，严格符合 schema！
```

**跟普通 Function Calling 的区别**：

| | 普通 Function Calling | Structured Outputs |
|------|---------------------|-------------------|
| JSON 保证 | "尽力而为" | **100% 保证** |
| 额外字段 | 可能出现 | 绝不可能 |
| 缺失必填字段 | 偶尔发生 | 绝不可能 |
| 适用场景 | 调工具（容错性高） | 结构化提取、分类 |
| 模型支持 | 所有模型 | GPT-4o+ 专属 |

### 10.2 Tool Choice — 强制 LLM 调用特定工具（2024）

```python
# 有时候你明确知道要调哪个工具，不希望 LLM 瞎选

# ① 强制调用 — 不调工具就不行
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "你好"}],  # ← 寒暄
    tools=[get_fridge_tool()],
    tool_choice="required",  # ← 强制！即使 "你好" 也必须调工具
)
# LLM 被迫调 get_fridge_inventory，哪怕用户只是打招呼


# ② 强制调用指定工具
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "冰箱里有什么？"}],
    tools=[get_fridge_tool(), search_recipes_tool(), ...],
    tool_choice={
        "type": "function",
        "function": {"name": "get_fridge_inventory"}  # ← 只用这个
    },
)
# 其他工具全部忽略，LLM 必须调 get_fridge_inventory


# ③ 禁用工具 — 纯文字模式
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "讲个笑话"}],
    tools=[...],
    tool_choice="none",  # ← 禁用所有工具，LLM 只能文字输出
)


# ④ 自动（默认）
# tool_choice="auto"  — LLM 自己决定调不调、调哪个
```

### 10.3 Streaming + Tool Calls — 流式工具调用（2024）

传统 Function Calling 只能等完整响应。现在可以**边流式输出边拼接工具调用参数**：

```python
# LLM 一边想，一边往外蹦 tool_call 的片段
async for chunk in stream:
    delta = chunk.choices[0].delta

    if delta.tool_calls:
        for tc_delta in delta.tool_calls:
            idx = tc_delta.index   # ← 第几个工具调用（0, 1, 2...）

            # 片段式拼接
            if idx not in tool_call_chunks:
                tool_call_chunks[idx] = {
                    "id": tc_delta.id or "",
                    "name": "",
                    "arguments": "",
                }

            if tc_delta.function:
                if tc_delta.function.name:
                    tool_call_chunks[idx]["name"] += tc_delta.function.name
                    # 可能分多次收到: "get_" → "fridge_" → "inventory"

                if tc_delta.function.arguments:
                    tool_call_chunks[idx]["arguments"] += tc_delta.function.arguments
                    # JSON 参数也是逐片来的: '{"user' → '_id":' → '"u1"}'

    if delta.content:
        # 纯文字也同时在流式输出
        full_text += delta.content

# 最终拼成完整调用
# → tool_call_chunks = {
#     0: {"id": "call_abc", "name": "get_fridge_inventory",
#         "arguments": '{"user_id": "u1"}'}
#   }
```

**这对用户体验的影响**：

```
传统（等全部完成）:
  用户发送 → 等 3 秒 → 全部回答一下出来

流式工具调用:
  用户发送 → 0.5秒 → "正在查询冰箱库存..." → 1秒 → 结果 → 开始打字
          ↑ LLM 先输出一句"准备文字"，然后调工具，结果回来后继续
```

### 10.4 DeepSeek Reasoning — 必须回传思考内容（2025）

DeepSeek 的推理模式（deepseek-reasoner）有一个特殊机制：

```python
# DeepSeek 推理模型会在 tool_call 之前输出 reasoning_content
response = await client.chat.completions.create(
    model="deepseek-reasoner",
    messages=messages,
    tools=tools,
)

msg = response.choices[0].message

# msg.content = None           ← 调工具时正常是 None
# msg.reasoning_content = "... 用户想查冰箱库存，我应该先调 get_fridge_inventory ..."
#                          ↑ DeepSeek 特有：思考过程

# ⚠️ 关键：必须在回传的 assistant 消息里带上 reasoning_content
messages.append({
    "role": "assistant",
    "content": msg.content,
    "tool_calls": [...],
    "reasoning_content": msg.reasoning_content,  # ← 不传这个，API 报 400！
})

# 如果不传：
# → openai.BadRequestError: reasoning_content is required
```

**你项目的处理**（base_agent.py:472）：

```python
assistant_msg = {
    "role": "assistant",
    "content": msg.content or "",
    "tool_calls": [...],
}
# DeepSeek thinking 模式：必须回传 reasoning_content
if hasattr(msg, "reasoning_content") and msg.reasoning_content:
    assistant_msg["reasoning_content"] = msg.reasoning_content
```

### 10.5 Parallel Tool Calling — 显式控制（2024）

```python
# 旧方式：LLM 自己决定是否并行
# 新方式：你可以显式控制

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    parallel_tool_calls=True,   # ← 允许 LLM 并行调多个工具（默认）
)

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    parallel_tool_calls=False,  # ← 禁止并行，一次只能调一个工具
)
```

**什么时候禁用并行？**

```
允许并行: "查冰箱库存 + 查家电状态" → 两个不冲突 → 一起跑 ✅
禁止并行: "创建购物清单 → 根据清单比价" → 第二步依赖第一步结果 → 必须串行
```

### 10.6 Computer Use — 不只调函数，操控电脑（Anthropic 2024.10）

这是 Function Calling 概念的最高级形态：

```
传统 Function Calling:
  LLM → 调你的函数 → 查数据库 / 调 API

Computer Use:
  LLM → 看到屏幕截图 → 移动鼠标 → 点击按钮 → 输入文字 → 看到新截图 → 继续操作
  ↑ 不是调你定义的函数，是像人一样操作任何软件
```

目前只有 Anthropic Claude 支持，但这是方向——未来你的 Agent 不只调你写的 `get_fridge_inventory()`，而是帮你在美团 App 上点来点去完成下单。

### 10.7 各厂商支持对比（2025）

| 能力 | OpenAI | DeepSeek | Anthropic | Google |
|------|--------|---------|-----------|--------|
| 基础 Function Calling | ✅ | ✅ | ✅ | ✅ |
| 并行调用 | ✅ | ✅ 默认 | ✅ | ✅ |
| Strict Mode | ✅ | ❌ | ❌ | ❌ |
| Structured Outputs | ✅ | ❌ | ❌ | ❌ |
| Tool Choice (强制) | ✅ | 部分 | ✅ | ✅ |
| 流式 Tool Calls | ✅ | ✅ | ✅ | ✅ |
| Reasoning 回传 | ❌ | ✅ 必须 | ❌ | ❌ |
| Computer Use | ❌ | ❌ | ✅ | ❌ |
| Prompt Caching | ✅ | ✅ | ✅ | ✅ |

---

## 11. 技术成熟度阶梯

```
Lv.1  定义工具 + 单次调用 ───── 最基本的       ← Hello World
Lv.2  + 并行工具调用 ───────── 效率提升         ← 你有
Lv.3  + 安全护栏（危险等级）── 人在回路         ← 你有
Lv.4  + 参数校验 + 自动修复 ── 容错            ← 你有
Lv.5  + ReAct 多轮循环 ────── 自主决策链       ← 你有
Lv.6  + 流式 Tool Calls ───── 体验提升         ← 你有
Lv.7  + Tool Choice 强制 ──── 精准控制         ← 部分
Lv.8  + Structured Outputs ── 100% 可靠        ← DeepSeek 不支持
Lv.9  + 多 Agent 工具协作 ─── 复杂任务拆分      ← 你有过（已合并为统一Agent）
Lv.10 + Computer Use ──────── 操控任何软件      ← 未来方向

你现在在 Lv.6，对家务 AI 管家完全够用。
Lv.8+ 受限于 DeepSeek API 能力边界，短期不用追。

---

## 12. 2025-2026：Function Calling 之后是什么？

说实话，2025-2026 年 **Function Calling 这个机制本身没有变**——定义 JSON Schema、LLM 选工具、执行回调——这个模型从 2023 年到现在没变过。变的是**工具怎么被发现、怎么共享、Agent 之间怎么协作**。

### 12.1 MCP（Model Context Protocol）— 工具的"USB 接口"（Anthropic 2024.11，2025 成为标准）

这是两年来最重大的架构变化。**MCP 解决的核心问题**：每接入一个新工具，你都要手写 JSON Schema + 函数实现。MCP 把它标准化了。

```
没有 MCP 的时代:
  你想接入"Gmail 发邮件" → 手写 OAuth + API 文档 → 手写 JSON Schema → 注册到 ToolRegistry
  你想接入"Google Drive 读文件" → 再来一遍...
  你想接入"GitHub 提 Issue" → 再来一遍...
  ↑ 每接一个新服务，都要从头写胶水代码

MCP 时代:
  任何工具提供方写一个 MCP Server（标准化的 JSON-RPC 接口）
  ↓
  你的 Agent 通过 MCP Client 连上去
  ↓
  Agent 自动发现: "这个 Server 提供了 3 个工具: send_email, read_drive, search_drive"
  ↓
  不需要手写 JSON Schema！工具定义是 Server 自己告诉你的
```

```
┌─────────────────────────────────────────────────────┐
│                  你的 Agent（MCP Client）             │
│                                                      │
│  tools = await mcp_client.list_tools()               │
│  # 自动发现: [send_email, read_drive, create_issue]  │
│                                                      │
│  result = await mcp_client.call_tool(                 │
│      "send_email", {"to": "xxx", "body": "..."}      │
│  )                                                    │
└──────────┬────────────┬────────────┬────────────────┘
           │            │            │
    ┌──────┴──┐  ┌──────┴──┐  ┌──────┴──┐
    │  Gmail  │  │  Drive  │  │ GitHub  │
    │  MCP    │  │  MCP    │  │  MCP    │
    │ Server  │  │ Server  │  │ Server  │
    └─────────┘  └─────────┘  └─────────┘
```

**对你的意义**：如果你想给 Agent 加"帮我在美团下单"的能力，不用自己研究美团 API 了，等美团出一个 MCP Server 就行。**工具从"你我写死"变成了"即插即用"。**

### 12.2 A2A（Agent-to-Agent Protocol）— Agent 之间的"普通话"（Google 2025.4）

MCP 解决的是"Agent 怎么用工具"。A2A 解决的是"Agent 之间怎么协作"。

```
没有 A2A:
  你的 Agent 无法调用别人的 Agent
  做菜谱规划时，你想让"美团 Agent"帮搜价格 → 做不到（接口不互通）

有 A2A:
  ① 你的 Agent 通过 A2A 发现附近有"美团价格 Agent"
  ② 发送 A2A 消息: "帮我查番茄在叮咚和美团的价格"
  ③ 美团 Agent 执行查询，返回标准化结果
  ④ 你的 Agent 拿到结果，生成最终回答
```

```
┌──────────────────┐    A2A     ┌──────────────────┐
│  你的家务 Agent    │◄──────────┤  美团价格 Agent    │
│                  │──────────►│                  │
│ "帮我比价"        │  请求报价   │ "番茄 叮咚4.5元"  │
└──────────────────┘           └──────────────────┘
```

**对你的意义**：你不需要自己写所有的工具。未来你只写"家电控制"和"冰箱管理"等家庭特有的工具，购物比价、快递追踪等通用能力可以直接调别人的 Agent。

### 12.3 OpenAI Agents SDK — Agent 开发的"Spring Boot"（2025.3）

OpenAI 把之前散落在 Cookbook 里的最佳实践打包成一个正式框架：

```python
from agents import Agent, Runner, function_tool


# 定义工具 — 跟 FastAPI 一样的装饰器风格
@function_tool
def get_fridge_inventory(user_id: str) -> list[dict]:
    """查看冰箱库存"""
    return [...]

@function_tool
def search_recipes(query: str, meal_type: str = "") -> list[dict]:
    """搜索菜谱"""
    return [...]


# 创建 Agent — 声明式
household_agent = Agent(
    name="家务管家",
    instructions="你是家务AI管家，口语化回复...",
    tools=[get_fridge_inventory, search_recipes],
)

# 运行 — 自动处理 ReAct 循环
result = await Runner.run(household_agent, "冰箱里有什么？")
print(result.final_output)  # → "您冰箱里有菠菜..."

# 框架自动做了:
# ① 工具转换为 OpenAI JSON Schema
# ② ReAct 循环（调LLM→调工具→回传→再调LLM）
# ③ 流式输出
# ④ 错误处理
# ⑤ 追踪
```

**跟你的自研 ReAct 循环对比**：

| | 你的自研 | OpenAI Agents SDK |
|------|---------|-------------------|
| 灵活性 | ⭐⭐⭐⭐⭐ 完全可控 | ⭐⭐⭐ 受限于框架 |
| 代码量 | 1400 行 | 50 行 |
| 学习曲线 | 需要理解 ReAct | 声明式，开箱即用 |
| 定制化 | 深度检查（死循环、安全护栏） | 框架内置但不灵活 |
| 厂商锁定 | 无（用 DeepSeek 也没问题） | 锁定 OpenAI |

**你不需要换**——你的自研 ReAct 循环的定制深度（安全护栏、自动修复、视频卡片注入、偏好提取）是通用框架做不到的。但知道有这个选项就行。

### 12.4 多模态 Function Calling（2025-2026）

LLM 不仅看文字，还能看图片来决定调什么工具：

```python
# 传统: 用户说 "冰箱里有什么" → LLM 调 get_fridge_inventory

# 多模态: 用户拍冰箱照片 → LLM 看图识别 → 自动调 add_fridge_item
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "我刚买了这些东西，帮我加入冰箱"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
        ]
    }],
    tools=[add_fridge_item, ...],
)
# LLM 看了图片 → 识别出菠菜、番茄、鸡蛋 →
# 自动调 add_fridge_item("菠菜", quantity=0.5) → add_fridge_item("番茄", quantity=3) → ...
```

**你的项目已经有了雏形**（`analyze_image` 工具），但走的是"先调视觉工具识别 → 再调入库工具"的两步模式。多模态 Function Calling 把这两步合并了——模型直接看图决定调什么。

### 12.5 总结：2026 年 Function Calling 的格局

```
2023: Function Calling 诞生（OpenAI 首发）
  └─ 定义工具 + LLM 选择 + 执行回调

2024: 成熟化
  ├─ Structured Outputs（100% 可靠 JSON）
  ├─ Streaming Tool Calls（流式工具调用）
  ├─ Parallel Tool Calling（显式并行控制）
  └─ MCP 发布（工具标准化）

2025-2026: 生态化
  ├─ MCP 成为行业标准（Anthropic + OpenAI + Google 都支持）
  ├─ A2A 协议（Agent 间互操作）
  ├─ Agents SDK 正式发布
  ├─ 多模态 Function Calling（看图调工具）
  └─ 工具市场 / 工具发现（像 App Store 一样装工具）

Function Calling 机制本身已稳定，变的是"工具从哪来、怎么共享"。
```

> **对你的项目来说**：你现在的 Function Calling 实现（自研 ReAct + ToolRegistry + 安全护栏）在机制层面已经完备。2026 年需要关注的是 **MCP 协议**——如果未来想让 Agent 接入更多外部服务（外卖、快递、电商），用 MCP 比自己写工具胶水代码优雅得多。
```
