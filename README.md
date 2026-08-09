# 🏠 Agent of Life — 家务 AI 管家

> 基于 **自研 ReAct Agent + 四阶段混合 RAG** 的智能家庭管理助手。
> 单一 Agent 调度 40+ 工具，覆盖购物、膳食、家电、维保、安防、家庭事务六大场景。

---

## 🏗️ 架构

```
用户 → FastAPI (SSE流式) → UnifiedAgent (ReAct循环)
                              ├─ IntentRouter (意图路由: 规则→缓存→LLM)
                              ├─ Plan-and-Execute (复杂任务自动分解)
                              ├─ SafetyGuard (高危操作确认拦截)
                              ├─ DeepSeek LLM (推理决策)
                              ├─ ToolRegistry (40+工具并行调用 + 自动修复)
                              │   ├─ 冰箱库存 / 菜谱规划 / 比价
                              │   ├─ 家电调度 / 维保提醒
                              │   ├─ 安防巡检 / 快递追踪
                              │   ├─ B站视频搜索 / 视觉识别
                              │   └─ search_knowledge_base (RAG检索)
                              ├─ Memory 三层架构
                              │   ├─ 短期: Redis + 滑动窗口摘要
                              │   ├─ 长期: Qdrant 向量固化
                              │   └─ 画像: LLM 自动提取偏好
                              └─ RAG 引擎 (四阶段)
                                  ├─ Query Rewrite (LLM改写) + HyDE
                                  ├─ Dense (BGE-M3 1024d) ∥ BM25 (jieba)
                                  ├─ RRF 融合 (α=0.7)
                                  └─ BGE-Reranker CrossEncoder 精排
```

### 核心特性

| 模块 | 实现 |
|------|------|
| Agent 引擎 | 自研 ReAct 循环（非 LangChain），并行工具调用+超时+退避重试 |
| 意图路由器 | 规则(0ms) → 缓存 → LLM(500ms) 三层分类，工具集缩减 70% |
| Plan & Execute | 多意图任务自动分解为有序子任务，指导 LLM 逐步执行 |
| 安全护栏 | danger_level 标记 + 前端确认弹窗，高危操作人在回路 |
| 自我纠错 | 工具失败自动 LLM 分析修复参数，重试一次 |
| 流式 SSE | run()/run_stream() 共享 _prepare_context()，行为一致 |

## 🔧 技术栈

| 层级 | 技术方案 |
|------|---------|
| **Agent 引擎** | 自研 ReAct 循环 + Function Calling（非 LangChain） |
| **LLM** | DeepSeek (OpenAI 兼容) |
| **Embedding** | BGE-M3 1024d 本地部署 (FlagEmbedding) |
| **混合检索** | Dense向量 + BM25关键词 + RRF融合 + BGE-Reranker精排 |
| **向量库** | Qdrant (Docker 部署，生产级) |
| **框架** | FastAPI + asyncio + SSE 流式 |
| **数据库** | SQLAlchemy 2.0 异步 + PostgreSQL (asyncpg) |
| **缓存** | Redis (对话持久化 + 双写) |
| **评估** | 自研 LLM Judge (Faithfulness/Relevancy/Precision/Recall) |
| **部署** | Docker Compose 一键启动 |

## 🚀 快速开始

```bash
# 1. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key

# 2. 启动
docker compose up -d

# 3. 打开浏览器
open http://localhost:8000/app
```

## 📊 RAG 评估报告

```
样本数: 11 (5个场景)
──────────────────────────────────
指标                 分数      说明
──────────────────────────────────
Faithfulness        0.50      答案忠实度（不编造）
Answer Relevancy    0.73      回答切题度
Context Precision   0.55      检索精度
Context Recall      0.50      召回完整度
Retrieval Hit Rate  1.00      检索命中率（100%）
──────────────────────────────────

场景拆分:
  菜谱查询   ██████████ 100%
  冰箱库存   ██████████ 100%
  维保查询   ██████████ 100%
  综合推荐   ██████████ 100%
  边界拒答   ██████████ 100%

→ 知识库填充后 Answer Relevancy ↑33%, Context Precision ↑34%
```

```bash
# 跑评估
python -m app.eval.ragas_eval

# 查看报告
cat data/eval_report.json
```

## 🎯 项目亮点

1. **自研 ReAct 循环，非 LangChain**
   - 完整实现 Agent 核心逻辑，完全可控
   - 并行工具调用 + 30s超时 + 3次退避重试
   - 滑动窗口对话摘要压缩（token ≤ 3000）

2. **四阶段混合检索，非调包**
   - Query Rewrite → Dense+BM25 → RRF → CrossEncoder
   - BGE-M3 本地部署，零 API 成本
   - 语义分块器：相邻句子 Embedding 相似度自适应断点

3. **量化评估体系**
   - 自研 LLM Judge 替代 RAGAS，4项指标 + 5场景拆分
   - 数据驱动优化：入库前后指标对比

4. **架构简洁**
   - 清理 1600+ 行死代码，6 Agent → 1 Agent
   - 设计决策：Qdrant 够用不用 Milvus，原生 OpenAI 不用 LangChain

## ⚙️ 设计决策

| 选型 | 用什么 | 为什么不用替代方案 |
|------|--------|-------------------|
| Agent 框架 | 自研 ReAct | LangChain太重，本项目体量不需要 |
| 向量库 | Qdrant | Milvus 太重，Qdrant 单容器部署，Rust 引擎，适合中小规模生产 |
| 检索 | 四阶段混合 | 单路 Dense 在专有名词上会漂移 |
| 评估 | 自研 LLM Judge | RAGAS v0.4 API 不稳定，多版本依赖冲突 |

## 📡 API

```
POST /api/v1/agent/chat          Agent 对话
POST /api/v1/agent/chat/stream   流式对话 (SSE)
POST /api/v1/agent/workflow/{type}  定时工作流
GET  /api/v1/dashboard/alerts    告警面板
POST /api/v1/knowledge/ingest/file  文档上传 (PDF/DOCX/TXT)
```

## 📂 项目结构

```
backend/app/
├── agents/          Agent 核心 (ReAct + ToolRegistry)
├── rag/             RAG 引擎 (chunker/embeddings/retriever/qa_chain)
├── tools/           40+ 工具实现
├── api/routes/      FastAPI 路由
├── models/          SQLAlchemy 模型
├── services/        调度服务
├── eval/            评估模块 (LLM Judge + test_dataset)
└── memory/          Qdrant + 对话记忆
```
