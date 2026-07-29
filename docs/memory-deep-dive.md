# Agent of Life - 记忆系统深度解析

> 三层记忆: 短期(Redis) -> 长期(Qdrant) -> 画像(PostgreSQL)
> 3 核心文件, 759 行 | Redis双写 + LLM摘要固化 + 自动偏好学习

---

## 目录

1. 整体架构
2. 消息写入: 双写机制
3. 消息读取: 分层降级
4. 记忆固化: 自动摘要
5. 长期记忆检索
6. 偏好自动学习
7. 语义缓存
8. 用户画像
9. 向量存储层
10. 完整记忆流转图
11. 关键文件索引

---

## 1. 整体架构

三层记忆, 按生命周期递减:

| 层级 | 存储 | 生命周期 | 容量 | 内容 |
|------|------|------|------|------|
| 短期 | 内存dict + Redis list | 会话期间(Redis 7天TTL) | 最近40条 | 原始对话消息 |
| 长期 | Qdrant 向量库 | 90天 | 不限 | LLM生成的对话摘要 |
| 画像 | PostgreSQL users表 | 永久 | 每用户一条 | 口味/过敏/预算等结构化偏好 |

核心文件:

| 文件 | 行数 | 职责 |
|------|:--:|------|
| memory/conversation_memory.py | 464 | 双写+固化+检索+偏好提取+语义缓存 |
| memory/vector_store.py | 206 | Qdrant向量存储: upsert/search/delete |
| memory/user_profile.py | 89 | PostgreSQL用户画像: get/create/update |

---

## 2. 消息写入: 双写机制

文件: conversation_memory.py add_message()

每条对话消息写入时, 同时写两层:

1. session->user映射: _session_users[session_id] = user_id
2. 内存写入: _memory[session_id].append(message), 超过40条trim
3. Redis持久化: LPUSH -> LTRIM(0,39) -> EXPIRE(7天), pipeline批量
4. 触发固化检测: 消息>=6条? -> asyncio.create_task(后台固化)

为什么双写? 内存零延迟(同一会话内), Redis服务重启后恢复上下文。

---

## 3. 消息读取: 分层降级

文件: conversation_memory.py get_history()

读取优先级: 内存(0ms) -> Redis恢复 -> 空列表

Redis恢复时: LRANGE读取 -> reversed()还原顺序(LPUSH是倒序) -> JSON解析 -> 回写内存热缓存

---

## 4. 记忆固化: 自动摘要

### 触发条件 (两个都要满足)

1. 消息数 >= memory_consolidation_threshold (默认6条)
2. 距上次固化 >= 5分钟 (防抖)

### 固化流程

1. 取最近10条消息, 拼成对话文本 (每条截断300字)
2. LLM生成摘要: System Prompt要求提取用户偏好/习惯, 重要事实/事件, 待办事项。max_tokens=200, temperature=0.1。输出格式: [记忆摘要 | 07/29 14:30] 用户偏好川菜, 忌香菜...
3. 存入Qdrant向量库: text=摘要, metadata={user_id, session_id, type:memory_consolidation, timestamp, ttl_days:90}

LLM不可用时的降级: 规则提取, 截取对话前200字符。
防抖: _summary_cache记录上次固化时间, 5分钟内不重复。

---

## 5. 长期记忆检索

### retrieve_user_memories() - Agent调用的主入口

1. 构建搜索查询: query为空时 -> 用户偏好 重要事实 待办事项 {user_id}
2. vector_store.search(search_query, top_k)
3. user_id过滤: 只返回该用户的记忆
4. 排序: score降序 -> timestamp降序
5. 返回top_k条 [{text, score, timestamp, session_id, type}]

### retrieve_user_summary() - Agent启动时注入

调用 retrieve_user_memories(top_k=8), 格式化为:

## 用户长期记忆（跨会话）
1. [07-15] 用户偏好川菜，忌香菜，月预算3000元
2. [07-10] 空调滤网上次清洗是3月，该保养了
3. [07-08] 待办：下周三社区物业费到期

这段文本注入到system prompt中, Agent在对话开始就了解用户背景。

---

## 6. 偏好自动学习

文件: conversation_memory.py extract_and_update_preferences()

每次对话结束后, Agent在后台异步调用:

Agent.run()善后 -> _schedule_preference_extraction()
  防抖: 同一用户10分钟内不重复
  -> asyncio.create_task(_extract_preferences_bg())
    -> mem.extract_and_update_preferences()

### 提取流程

1. LLM分析对话: System Prompt要求只提取明确变化信号(关键词: 改变/现在/已经/最近/不), 输出JSON {preferences, allergies, disliked, budget, summary}
2. 检查变化: preferences/allergies/disliked/budget任一不为空?
3. 写回PostgreSQL: UserProfileManager.update_preferences() -> set union去重合并

关键: 只提取变化信号(不提取静态描述), JSON容错(处理markdown包裹), 失败静默跳过。

---

## 7. 语义缓存

内存级 query->response 缓存, 非Redis非Qdrant:

key = md5(session_id + normalized_query[:200])
TTL = 5分钟, LRU淘汰超500条

适用: 用户5分钟内反复问相同问题, 避免重复调LLM。

---

## 8. 用户画像

文件: memory/user_profile.py (89行)

PostgreSQL users表的CRUD封装:

- get_profile(user_id): 查users表 -> UserProfile对象
- get_or_create(user_id, name): 有则返回, 无则创建默认画像
- update_preferences(): 偏好去重合并(set union), 写回PostgreSQL

存储字段: name, family_size, dietary_preferences(JSON), allergies(JSON), disliked_foods(JSON), budget_monthly, preferred_supermarkets(JSON), city, location

---

## 9. 向量存储层

文件: memory/vector_store.py (206行)

Qdrant纯存储引擎, BGE-M3预计算所有向量:

| 操作 | 流程 |
|------|------|
| add() | 构建PointStruct(id+vector1024d+payload) -> client.upsert() |
| search() | query->BGE-M3.encode->client.query_points()->返回{id,text,metadata,score} |
| delete() | client.delete(PointIdsList) |

Fallback: Qdrant不可用时 -> 内存list + numpy手算余弦相似度。

记忆数据在Qdrant中的存储格式:

Point:
  id: uuid
  vector: [0.12, -0.34, ...] (1024d BGE-M3)
  payload:
    text: [记忆摘要 | 07/29 14:30] 用户偏好川菜...
    user_id: usr_abc
    session_id: sess_usr_abc_1722
    type: memory_consolidation
    timestamp: 2026-07-29T14:30:00
    ttl_days: 90

---

## 10. 完整记忆流转图

```
用户发消息
  -> 短期记忆(内存+Redis): add_message() 双写, 40条/会话
  -> 触发固化(>=6条且>5分钟): LLM摘要 -> BGE-M3 -> Qdrant
  -> 长期记忆(Qdrant): 语义搜索+user_id过滤, 90天TTL
  -> 注入System Prompt: retrieve_user_summary() top-8 -> _build_full_prompt()
```

```
偏好学习(独立并行):
  Agent.run()善后 -> extract_and_update_preferences()
  -> LLM提取变化 -> UserProfileManager.update()
  -> PostgreSQL users表(永久)
```

---

## 11. 关键文件索引

| 文件 | 行数 | 核心职责 |
|------|:--:|------|
| memory/conversation_memory.py | 464 | 双写+固化+检索+偏好提取+语义缓存 |
| memory/vector_store.py | 206 | Qdrant: upsert/search/delete + Fallback |
| memory/user_profile.py | 89 | PostgreSQL画像: get/create/update |

### 关键配置

| 配置 | 默认值 | 说明 |
|------|------|------|
| redis_url | redis://localhost:6379/0 | Redis连接 |
| conversation_history_limit | 40 | 每会话最大消息数 |
| memory_consolidation_threshold | 6 | 触发固化的消息数 |
| memory_long_term_ttl_days | 90 | 长期记忆保留天数 |