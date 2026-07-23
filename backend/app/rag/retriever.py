"""
检索器 v4.0 — 混合检索 (Dense Vector + BM25 Sparse) + RRF 融合 + BGE Reranker
支持 Query Rewrite、多路召回、自适应权重
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

from loguru import logger

from ..config import settings
from ..memory.vector_store import get_vector_store


class HybridRetriever:
    """混合检索引擎 — Dense + Sparse + Rerank 三阶段流水线"""

    def __init__(
        self,
        top_k: int | None = None,
        use_rerank: bool | None = None,
    ):
        self.top_k = top_k or settings.final_top_k
        self.candidate_k = settings.retrieval_top_k
        self.use_rerank = use_rerank if use_rerank is not None else settings.use_reranker
        self.hybrid_alpha = settings.hybrid_alpha
        self.vector_store = get_vector_store()
        self._bm25_index = None
        self._bm25_docs: list[str] = []
        self._bm25_corpus_ids: list[str] = []

    # ================================================================
    # 阶段 0: Query Rewrite — 查询改写增强召回
    # ================================================================

    async def _rewrite_query(self, query: str) -> list[str]:
        """多角度查询改写 (Multi-Query / HyDE 简化版)

        生成 3-5 个改写查询，扩大语义覆盖面
        """
        queries = [query]  # 原始查询必保留

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.openai_base_url,
                timeout=5.0,  # 快速超时，不阻塞检索
            )
            resp = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是查询改写助手。将用户问题改写成2-4个不同角度的检索查询，"
                        "每行一个，用中文。不要编号，不要解释。"
                    ),
                }, {
                    "role": "user",
                    "content": f"原始问题：{query}",
                }],
                temperature=0.3,
                max_tokens=200,
            )
            rewritten = resp.choices[0].message.content or ""
            for line in rewritten.strip().split("\n"):
                line = line.strip()
                if line and line not in queries and len(line) > 2:
                    queries.append(line)
        except Exception as e:
            logger.debug(f"Query rewrite skipped: {e}")

        return queries[:5]

    # ================================================================
    # 阶段 1: Dense 向量召回
    # ================================================================

    async def _dense_retrieve(self, queries: list[str]) -> dict[str, dict]:
        """多查询向量召回 + 分数融合"""
        all_results: dict[str, dict] = {}

        from .embeddings import get_embedding_generator
        embedder = get_embedding_generator()

        for qi, query in enumerate(queries):
            results = await self.vector_store.search(query, top_k=self.candidate_k)
            # 原始查询权重 1.0，改写查询权重 0.7
            weight = 1.0 if qi == 0 else 0.7
            for r in results:
                doc_id = r.get("id", r.get("text", ""))
                if doc_id not in all_results:
                    all_results[doc_id] = {**r, "dense_score": r.get("score", 0) * weight}
                else:
                    all_results[doc_id]["dense_score"] = max(
                        all_results[doc_id].get("dense_score", 0),
                        r.get("score", 0) * weight,
                    )

        return all_results

    # ================================================================
    # 阶段 2: BM25 稀疏召回
    # ================================================================

    def _ensure_bm25_index(self):
        """确保 BM25 索引已构建"""
        if self._bm25_index is not None:
            return

        # 收集所有已索引文档
        all_docs = []
        all_ids = []
        try:
            if self.vector_store.collection and self.vector_store.collection.count() > 0:
                data = self.vector_store.collection.get()
                for doc_id, doc_text in zip(data.get("ids", []), data.get("documents", [])):
                    all_ids.append(doc_id)
                    all_docs.append(doc_text)
        except Exception:
            pass

        # Fallback 存储
        for doc in getattr(self.vector_store, "_fallback_store", []):
            all_ids.append(doc.get("id", ""))
            all_docs.append(doc.get("text", ""))

        if all_docs:
            try:
                from rank_bm25 import BM25Okapi
                import jieba

                tokenized = [" ".join(jieba.cut(doc)) for doc in all_docs]
                self._bm25_index = BM25Okapi(
                    [t.split() for t in tokenized]
                )
                self._bm25_docs = all_docs
                self._bm25_corpus_ids = all_ids
                logger.debug(f"BM25 index built with {len(all_docs)} docs")
            except ImportError:
                logger.warning("rank-bm25 not installed, BM25 disabled")
            except Exception as e:
                logger.warning(f"BM25 index build failed: {e}")

    def _bm25_search(self, query: str) -> list[dict[str, Any]]:
        """BM25 关键词检索"""
        self._ensure_bm25_index()
        if not self._bm25_index:
            return []

        try:
            import jieba
            tokenized = " ".join(jieba.cut(query)).split()
            scores = self._bm25_index.get_scores(tokenized)

            # 归一化
            max_score = max(scores) if max(scores) > 0 else 1
            results = []
            for i, score in enumerate(scores):
                if score > 0 and i < len(self._bm25_corpus_ids):
                    results.append({
                        "id": self._bm25_corpus_ids[i],
                        "text": self._bm25_docs[i] if i < len(self._bm25_docs) else "",
                        "bm25_score": float(score / max_score),
                    })
            results.sort(key=lambda x: x["bm25_score"], reverse=True)
            return results[:self.candidate_k]
        except Exception as e:
            logger.warning(f"BM25 search failed: {e}")
            return []

    # ================================================================
    # 阶段 3: RRF 融合 (Reciprocal Rank Fusion)
    # ================================================================

    def _rrf_fusion(
        self,
        dense_results: dict[str, dict],
        bm25_results: list[dict],
    ) -> list[dict[str, Any]]:
        """RRF 融合 Dense + Sparse 结果"""
        # 构建 BM25 排名
        bm25_ranks: dict[str, int] = {}
        for rank, r in enumerate(bm25_results):
            doc_id = r.get("id", "")
            if doc_id:
                bm25_ranks[doc_id] = rank + 1

        # 构建 Dense 排名 (按分数排序)
        dense_sorted = sorted(
            dense_results.items(),
            key=lambda x: x[1].get("dense_score", 0),
            reverse=True,
        )
        dense_ranks: dict[str, int] = {}
        for rank, (doc_id, _) in enumerate(dense_sorted):
            dense_ranks[doc_id] = rank + 1

        # RRF 公式
        all_ids = set(list(dense_ranks.keys()) + list(bm25_ranks.keys()))
        k = 60  # RRF 平滑参数

        fused = []
        for doc_id in all_ids:
            d_rank = dense_ranks.get(doc_id, len(dense_ranks) + 1)
            b_rank = bm25_ranks.get(doc_id, len(bm25_ranks) + 1)

            rrf_score = (
                self.hybrid_alpha / (k + d_rank)
                + (1 - self.hybrid_alpha) / (k + b_rank)
            )

            info = dense_results.get(doc_id, {})
            fused.append({
                **info,
                "id": doc_id,
                "rrf_score": round(rrf_score, 6),
                "dense_rank": d_rank,
                "bm25_rank": b_rank,
            })

        fused.sort(key=lambda x: x["rrf_score"], reverse=True)
        return fused[:self.candidate_k]

    # ================================================================
    # 阶段 4: Reranker Cross-Encoder 精排
    # ================================================================

    async def _rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """BGE-Reranker-v2 精排 (CrossEncoder, 兼容性更好)"""
        if not candidates or not self.use_rerank:
            return candidates

        try:
            import os as _os
            d_drive = str(settings.data_dir / "models" / "huggingface")
            if not _os.environ.get("HF_HOME"):
                _os.environ["HF_HOME"] = d_drive

            from sentence_transformers import CrossEncoder

            reranker = CrossEncoder(
                settings.reranker_model_name,
                device=settings.embedding_device,
            )

            pairs = [[query, cand.get("text", "")] for cand in candidates]
            scores = reranker.predict(pairs, show_progress_bar=False)

            # 归一化到 0-1
            import numpy as np
            if hasattr(scores, '__len__') and len(scores) > 0:
                scores_arr = np.array(scores, dtype=float)
                scores_min, scores_max = scores_arr.min(), scores_arr.max()
                if scores_max > scores_min:
                    scores_arr = (scores_arr - scores_min) / (scores_max - scores_min)
                each_score = [float(s) for s in scores_arr]
            else:
                each_score = [float(scores)]

            for i, score in enumerate(each_score):
                if i < len(candidates):
                    candidates[i]["rerank_score"] = round(score, 4)
                    candidates[i]["final_score"] = round(
                        candidates[i].get("rrf_score", 0) * 0.3 + score * 0.7, 4
                    )

            candidates.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        except ImportError:
            logger.debug("sentence-transformers CrossEncoder not available")
            for cand in candidates:
                cand["final_score"] = cand.get("rrf_score", 0)
            candidates.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        except Exception as e:
            logger.warning(f"Reranker failed: {e}")
            for cand in candidates:
                cand["final_score"] = cand.get("rrf_score", 0)

        return candidates

    # ================================================================
    # 主检索入口
    # ================================================================

    async def retrieve(
        self, query: str, filters: dict | None = None,
        min_dense_score: float = 0.45,  # 低于此分数视为不相关
    ) -> list[dict[str, Any]]:
        """完整的混合检索流水线"""
        if not query.strip():
            return []

        # Phase 1: Query Rewrite
        queries = await self._rewrite_query(query)
        logger.debug(f"Rewritten queries: {queries}")

        # Phase 2: Dense + BM25 并行召回
        dense_results, bm25_results = await asyncio.gather(
            self._dense_retrieve(queries),
            asyncio.to_thread(self._bm25_search, query),
        )

        # Phase 3: RRF 融合
        candidates = self._rrf_fusion(dense_results, bm25_results)
        logger.debug(f"After RRF fusion: {len(candidates)} candidates")

        # Phase 4: Reranker 精排
        candidates = await self._rerank(query, candidates)

        # Phase 5: 元数据过滤
        if filters:
            candidates = [
                c for c in candidates
                if all(
                    str(c.get("metadata", {}).get(k)) == str(v)
                    for k, v in filters.items()
                )
            ]

        # Phase 6: 相关度过滤 — 剔除语义不相关的结果
        candidates = [
            c for c in candidates
            if c.get("dense_score", 0) >= min_dense_score
        ]

        return candidates[:self.top_k]

    async def retrieve_context(
        self, query: str, filters: dict | None = None, max_chars: int = 3000
    ) -> str:
        """检索并拼接上下文"""
        docs = await self.retrieve(query, filters)
        if not docs:
            return ""

        parts = []
        total_chars = 0
        for i, doc in enumerate(docs):
            text = doc.get("text", "")
            score = doc.get("final_score", doc.get("rrf_score", 0))
            chunk = f"[文档{i+1}](相关度:{score:.2f}) {text}"
            if total_chars + len(chunk) > max_chars:
                # 截断最后的文档
                remaining = max_chars - total_chars - 50
                if remaining > 100:
                    chunk = chunk[:remaining] + "..."
                    parts.append(chunk)
                break
            parts.append(chunk)
            total_chars += len(chunk)

        return "\n\n---\n\n".join(parts)


# 全局单例
_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
