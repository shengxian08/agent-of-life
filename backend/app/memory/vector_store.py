"""
向量存储 v4.1 — ChromaDB + BGE-M3 Embedding 统一管道

关键设计：ChromaDB 禁用内置 Embedding，全部由 BGE-M3 预计算。
入库: chunk文本 → BGE-M3.encode() → 1024d向量 → ChromaDB
查询: query文本 → BGE-M3.encode() → 1024d向量 → ChromaDB.query(query_embeddings=...)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from ..config import settings
from loguru import logger


class VectorStore:
    """ChromaDB 向量存储 — 全部使用 BGE-M3 预计算 Embedding

    ChromaDB 被配置为纯存储引擎，不做任何内置编码。
    """

    def __init__(self, collection_name: str = "household_memory"):
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self._fallback_store: list[dict] = []
        self._init_store()

    def _init_store(self):
        if not CHROMA_AVAILABLE:
            return
        try:
            self.client = chromadb.PersistentClient(
                path=str(settings.vector_db_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )

            # 获取或创建 collection — 不再重建，只检查维度兼容性
            try:
                existing = self.client.get_collection(
                    self.collection_name, embedding_function=None
                )
                existing_count = existing.count()
                logger.info(
                    f"ChromaDB collection '{self.collection_name}' loaded "
                    f"({existing_count} docs, cosine space, BGE-M3 {settings.embedding_dim}d)"
                )
                self.collection = existing
                return
            except Exception:
                pass

            # 首次创建
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )
            logger.info(
                f"ChromaDB collection '{self.collection_name}' created "
                f"(cosine space, BGE-M3 {settings.embedding_dim}d, no built-in embedding)"
            )
        except Exception as e:
            logger.warning(f"ChromaDB init failed: {e}, using in-memory fallback")
            self.collection = None

    # ================================================================
    # 写入：chunk → BGE-M3 → ChromaDB
    # ================================================================

    async def add(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> list[str]:
        """添加文档到向量库

        流程: text → BGE-M3 embed (如未预计算) → ChromaDB.add(embeddings=...)

        Returns:
            实际使用的 doc ids
        """
        if not texts:
            return []

        if ids is None:
            ids = [f"doc_{datetime.now().timestamp():.0f}_{i}" for i in range(len(texts))]
        if metadatas is None:
            metadatas = [{}] * len(texts)

        # 如果没有预计算 embedding，用 BGE-M3 实时生成
        if embeddings is None and self.collection is not None:
            embeddings = await self._embed_texts(texts)

        # 写入 ChromaDB（只传 pre-computed embeddings，不让 chromadb 自己编码）
        if CHROMA_AVAILABLE and self.collection is not None and embeddings is not None:
            try:
                self.collection.add(
                    ids=ids,
                    documents=texts,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
                logger.debug(f"Added {len(texts)} docs to ChromaDB (BGE-M3 {settings.embedding_dim}d)")
                return ids
            except Exception as e:
                logger.warning(f"ChromaDB add failed, using fallback: {e}")

        # Fallback: 内存存储
        for i, text in enumerate(texts):
            self._fallback_store.append({
                "id": ids[i] if i < len(ids) else f"fb_{len(self._fallback_store)}",
                "text": text,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "embedding": embeddings[i] if embeddings and i < len(embeddings) else None,
            })
        return ids

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """用 BGE-M3 生成 embedding"""
        try:
            from ..rag.embeddings import get_embedding_generator
            gen = get_embedding_generator()
            result = await gen.embed_documents(texts)
            return result.get("dense_vecs", [])
        except Exception as e:
            logger.error(f"BGE-M3 embedding failed: {e}")
            return [[0.0] * settings.embedding_dim for _ in texts]

    # ================================================================
    # 查询：query → BGE-M3 → 向量搜索
    # ================================================================

    async def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        """BGE-M3 向量搜索

        流程: query → BGE-M3.encode() → [1024d] → ChromaDB.query(query_embeddings=...)
        """
        # Step 1: 用 BGE-M3 编码查询
        query_emb = await self._embed_query(query)
        if query_emb is None:
            return []

        results = []

        # Step 2: ChromaDB 向量搜索（用预计算的 query embedding）
        if CHROMA_AVAILABLE and self.collection is not None and self.collection.count() > 0:
            try:
                resp = self.collection.query(
                    query_embeddings=[query_emb],    # ← BGE-M3 编码的查询向量
                    n_results=min(top_k, self.collection.count()),
                    include=["documents", "metadatas", "distances"],
                )
                for doc, meta, dist, doc_id in zip(
                    resp.get("documents", [[]])[0],
                    resp.get("metadatas", [[]])[0],
                    resp.get("distances", [[]])[0],
                    resp.get("ids", [[]])[0],
                ):
                    score = round(max(0.0, 1.0 - dist), 4) if dist else 0.0
                    results.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": meta,
                        "score": score,
                    })
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}")

        # Step 3: Fallback 内存搜索（余弦相似度）
        if self._fallback_store:
            for doc in self._fallback_store:
                if doc.get("embedding"):
                    a, b = np.array(query_emb), np.array(doc["embedding"])
                    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
                    if sim > 0.1:
                        results.append({
                            "id": doc.get("id", ""),
                            "text": doc.get("text", ""),
                            "metadata": doc.get("metadata", {}),
                            "score": round(sim, 4),
                        })

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k]

    async def _embed_query(self, query: str) -> list[float] | None:
        """用 BGE-M3 编码查询文本 → 1024d 向量"""
        try:
            from ..rag.embeddings import get_embedding_generator
            gen = get_embedding_generator()
            return await gen.embed_query(query)
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return None

    # ================================================================
    # 管理
    # ================================================================

    async def delete(self, ids: list[str]) -> None:
        if CHROMA_AVAILABLE and self.collection:
            try:
                self.collection.delete(ids=ids)
                return
            except Exception:
                pass
        self._fallback_store = [d for d in self._fallback_store if d["id"] not in ids]

    @property
    def count(self) -> int:
        chroma_count = 0
        try:
            if self.collection:
                chroma_count = self.collection.count()
        except Exception:
            pass
        return chroma_count + len(self._fallback_store)


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
