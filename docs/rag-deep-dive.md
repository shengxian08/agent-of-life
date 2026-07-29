# Agent of Life - RAG 引擎深度解析

> 四阶段混合检索: Query Rewrite + Dense(BGE-M3) // BM25(jieba) -> RRF -> BGE-Reranker
> 4 核心文件, 1,314 行 | BGE-M3 本地部署, 1024d, 零 API 成本

---

## 目录

1. [整体架构](#1-整体架构)
2. [Embedding 引擎](#2-embedding-引擎)
3. [文档摄入](#3-文档摄入)
4. [语义分块器](#4-语义分块器)
5. [向量存储](#5-向量存储)
6. [混合检索流水线](#6-混合检索流水线)
7. [RAG 问答链](#7-rag-问答链)
8. [评估体系](#8-评估体系)
9. [关键文件索引](#9-关键文件索引)

---

## 1. 整体架构

| 文件 | 行数 | 职责 |
|------|:--:|------|
| rag/embeddings.py | 372 | BGE-M3: 4级降级加载 + Dense/Sparse编码 + LRU缓存 |
| rag/chunker.py | 182 | 语义分块: Embedding相似度自适应断点 |
| rag/retriever.py | 424 | 6阶段混合检索: Rewrite+Dense+BM25+RRF+Reranker+Filter |
| rag/qa_chain.py | 336 | RAG问答: 检索->质量门槛->生成/Fallback->自省 |
| memory/vector_store.py | 206 | Qdrant向量存储 + 内存Fallback |

数据流: 入库(文本->分块->BGE-M3->Qdrant) | 检索(问题->Rewrite+HyDE->Dense//BM25->RRF->Reranker->LLM)

---

## 2. Embedding 引擎 (embeddings.py 372行)

### 4 级自动降级加载

1. FlagEmbedding BGEM3FlagModel - 原生BGE-M3, Dense+Sparse双路, FP16, 本地路径 ./data/models/bge-m3-local
2. sentence-transformers - 通用降级, Dense only
3. ONNX Runtime - CPU推理加速2-3x, 需预导出模型
4. OpenAI API - 最后备选, text-embedding-3-small

### 懒加载 + 线程安全
首次调用触发加载(约2-5分钟, 2.2GB)。threading.Lock保证线程安全。

### LRU 查询缓存
embed_query() 内置缓存, 最多512条。重复查询命中率40-60%。

### 编码参数
batch_size=12, max_length=8192, 输出1024d Dense + 可选Sparse词权重

---

## 3. 文档摄入

### 菜谱入库 (启动时自动)
index_recipes_to_vectordb(): 50+道菜谱 -> 结构化文本 -> BGE-M3编码 -> Qdrant。去重: 检查source=recipe_db。

### 家电知识入库
index_knowledge_to_vectordb(): 8篇保养知识 -> 同上流程。

### 文档上传 (PDF/DOCX/TXT)
ingest_file() -> pdfplumber/docx提取 -> 中文占比检测(<10%拒绝) -> 语义分块 -> BGE-M3 -> Qdrant

---

## 4. 语义分块器 (chunker.py 182行)

### Semantic 分块算法

1. 按句号/感叹号/问号拆成句子列表
2. BGE-M3.encode(所有句子) -> N个1024d向量
3. 计算相邻句子余弦相似度
4. 自适应阈值 = mean(相似度) - std(相似度)
5. 相似度 < 阈值 -> 断点
6. 按断点切分 + chunk_size控制(默认800字)

优势: 在话题转换处切分, 保证chunk内部语义连贯。固定长度会在段落中间切断。

### 递归降级
分隔符优先级: 双换行 -> 单换行 -> 句号 -> 感叹号 -> 逗号 -> 空格。最后手段按长度强制切。

---

## 5. 向量存储 (vector_store.py 206行)

Qdrant 作为纯存储引擎: 不内置编码, 所有embedding由BGE-M3预计算传入。
collection: household_memory, dim=1024, distance=Cosine。
Fallback: Qdrant不可用时 -> 内存list + numpy手算余弦相似度。

---

## 6. 混合检索流水线 (retriever.py 424行)

### Phase 0: Query Rewrite + HyDE
_rewrite_query(): LLM生成3-4个变体查询(同义/具体化/抽象化), timeout=5s
_hyde_generate(): LLM生成50-100字假设答案作为额外查询, 可配置关闭
最终查询列表: [原query, 改写1-3, HyDE], 最多5个

### Phase 1: Dense 向量检索
每个查询 -> BGE-M3 -> Qdrant搜索(top_k=20)。原query权重1.0, 改写权重0.7。同文档取max pooling。

### Phase 2: BM25 关键词检索 (并行)
原query -> jieba分词 -> BM25Okapi索引。索引懒构建: 首次从Qdrant scroll全量(limit=10000)。
asyncio.gather 与 Phase1 并行执行。

### Phase 3: RRF 融合
RRF(d) = alpha/(k+rank_dense) + (1-alpha)/(k+rank_bm25)
alpha=0.7(偏Dense), k=60(平滑参数)

为什么排名融合: Dense分(余弦0~1)和BM25分(TF-IDF无上限)不可比, 排名是统一尺度。

### Phase 4: BGE-Reranker 精排
CrossEncoder(bge-reranker-v2-m3): query+doc拼一起逐token交互打分。
final = rrf*0.3 + rerank*0.7。可配置关闭。

为什么需要Reranker: Dense(双塔)无query-doc交互; Cross-Encoder逐token交叉注意力, 更准但更慢。粗排20候选->精排5最终。

### Phase 5-6: 过滤
元数据过滤(source/type) + 相关度阈值(dense_score < 0.35剔除)。返回top_k=5。

---

## 7. RAG 问答链 (qa_chain.py 336行)

### query() 流程

1. sources = await retriever.retrieve(question)  # 6阶段检索
2. top_score < 0.15 -> 清空context (低质量门槛)
3. 分支: context为空->Fallback(LLM自由回答,标注无记录); context不为空->RAG生成(基于文档,标注来源[N])
4. 可选: _reflect() 自省, LLM判断答案是否基于文档->YES/NO

### System Prompt 设计
正常RAG: 优先参考信息+标注来源+不编造数字+文档无信息说未记录
Fallback: 告知用户无记录+通用知识+家电优先安全+不确定诚实说

---

## 8. 评估体系 (eval/ragas_eval.py 255行)

自研 LLM Judge (替代RAGAS): 4项指标, 11条样本, 5个场景

| 指标 | 分数 | 说明 |
|------|:--:|------|
| Faithfulness | 0.50 | 答案忠实度 |
| Answer Relevancy | 0.73 | 回答切题度 |
| Context Precision | 0.55 | 检索精度 |
| Context Recall | 0.50 | 召回完整度 |
| Retrieval Hit Rate | 1.00 | 检索命中率 |

5场景命中率均100%。知识库填充后Relevancy+33%, Precision+34%。

---

## 9. 关键文件索引

| 文件 | 行数 | 核心职责 |
|------|:--:|------|
| rag/embeddings.py | 372 | BGE-M3: 4级降级 + Dense/Sparse + LRU缓存 |
| rag/chunker.py | 182 | 语义分块: 相似度断点 + 递归降级 |
| rag/retriever.py | 424 | 6阶段: Rewrite+HyDE+Dense+BM25+RRF+Reranker+Filter |
| rag/qa_chain.py | 336 | RAG问答: 检索->门槛->生成/Fallback->自省 |
| memory/vector_store.py | 206 | Qdrant存储 + 内存Fallback |
| tools/recipe_tools.py | 1635 | 菜谱 + 分词搜索 + 向量索引 |
| eval/ragas_eval.py | 255 | LLM Judge: 4指标 + 5场景 |
| eval/test_dataset.py | 102 | 11条测试样本 |

### 关键配置

| 配置 | 默认值 | 说明 |
|------|------|------|
| embedding_model_name | ./data/models/bge-m3-local | BGE-M3 本地路径 |
| embedding_dim | 1024 | 向量维度 |
| use_reranker | False | 是否启用Reranker |
| hybrid_alpha | 0.7 | RRF Dense权重 |
| retrieval_top_k | 20 | 候选数 |
| final_top_k | 5 | 最终返回数 |
| retrieval_min_dense_score | 0.35 | 最低相关度 |
| retrieval_use_hyde | True | 是否启用HyDE |