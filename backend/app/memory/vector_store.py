"""
向量存储 v5.0 — Qdrant + BGE-M3 Embedding

设计：Qdrant 纯存储引擎，BGE-M3 预计算所有向量。
入库: chunk → BGE-M3.encode() → 1024d → Qdrant.upsert
查询: query → BGE-M3.encode() → 1024d → Qdrant.search
"""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from loguru import logger

from ..config import settings

_qdrant_client = None


def _get_qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient
            _qdrant_client = QdrantClient(url=settings.qdrant_url, timeout=10.0)
            _qdrant_client.get_collections()
            logger.info(f"Qdrant connected: {settings.qdrant_url}")
        except ImportError:
            logger.warning("qdrant-client not installed. Run: pip install qdrant-client")
            _qdrant_client = None
        except Exception as e:
            logger.warning(f"Qdrant unavailable ({e}), using in-memory fallback")
            _qdrant_client = None
    return _qdrant_client


class VectorStore:
    """Qdrant 向量存储 — BGE-M3 预计算 Embedding"""

    def __init__(self, collection_name: str | None = None):
        self.collection_name = collection_name or settings.qdrant_collection
        self._dim = settings.embedding_dim
        self._fallback_store: list[dict] = []
        self._ensure_collection()

    def _ensure_collection(self):
        client = _get_qdrant()
        if client is None:
            return
        try:
            from qdrant_client.models import Distance, VectorParams
            collections = [c.name for c in client.get_collections().collections]
            if self.collection_name not in collections:
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
                )
                logger.info(
                    f"Qdrant collection '{self.collection_name}' created ({self._dim}d, cosine)"
                )
            else:
                self._collection_info = client.get_collection(self.collection_name)
                logger.info(
                    f"Qdrant collection '{self.collection_name}' loaded ({self._collection_info.points_count} points, {self._dim}d, cosine)"
                )
        except Exception as e:
            logger.warning(f"Qdrant collection init failed: {e}")

    @property
    def collection(self):
        """返回 Qdrant collection 对象（兼容旧代码直接访问 vs.collection）"""
        client = _get_qdrant()
        if client is None:
            return None
        try:
            return client.get_collection(self.collection_name)
        except Exception:
            return None

    @staticmethod
    def _to_uuid(pid: str) -> str:
        """将任意字符串 ID 转换为 Qdrant 接受的 UUID 格式"""
        import hashlib
        h = hashlib.md5(pid.encode()).hexdigest()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

    async def add(self, texts, metadatas=None, ids=None, embeddings=None):
        if not texts:
            return []
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        # Qdrant 只接受 uint 或 UUID，字符串 ID 统一转换
        ids = [self._to_uuid(pid) for pid in ids]
        if metadatas is None:
            metadatas = [{}] * len(texts)
        if embeddings is None:
            embeddings = await self._embed_texts(texts)
        client = _get_qdrant()
        if client is not None and embeddings:
            try:
                from qdrant_client.models import PointStruct
                points = [
                    PointStruct(
                        id=ids[i] if i < len(ids) else self._to_uuid(uuid.uuid4().hex),
                        vector=embeddings[i] if i < len(embeddings) else [0.0] * self._dim,
                        payload={"text": texts[i] if i < len(texts) else "", **(metadatas[i] if i < len(metadatas) else {})},
                    )
                    for i in range(len(texts))
                ]
                client.upsert(collection_name=self.collection_name, points=points)
                logger.debug(f"Qdrant: upserted {len(points)} points")
                return ids
            except Exception as e:
                logger.warning(f"Qdrant upsert failed: {e}")
        for i, text in enumerate(texts):
            self._fallback_store.append({
                "id": ids[i] if i < len(ids) else f"fb_{len(self._fallback_store)}",
                "text": text,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "embedding": embeddings[i] if embeddings and i < len(embeddings) else None,
            })
        return ids

    async def _embed_texts(self, texts):
        try:
            from ..rag.embeddings import get_embedding_generator
            gen = get_embedding_generator()
            result = await gen.embed_documents(texts)
            return result.get("dense_vecs", [])
        except Exception as e:
            logger.error(f"BGE-M3 embedding failed: {e}")
            return [[0.0] * self._dim for _ in texts]

    async def search(self, query, top_k=20):
        query_emb = await self._embed_query(query)
        if query_emb is None:
            return []
        results: list[dict[str, Any]] = []
        client = _get_qdrant()
        if client is not None:
            try:
                # qdrant-client >= 1.7 uses query_points(), older versions use search()
                if hasattr(client, 'query_points'):
                    resp = client.query_points(
                        collection_name=self.collection_name,
                        query=query_emb,
                        limit=top_k,
                    )
                    for point in resp.points:
                        results.append({
                            "id": str(point.id) if point.id else "",
                            "text": point.payload.get("text", "") if point.payload else "",
                            "metadata": {k: v for k, v in (point.payload or {}).items() if k != "text"},
                            "score": round(point.score, 4) if point.score else 0.0,
                        })
                elif hasattr(client, 'search'):
                    resp = client.search(
                        collection_name=self.collection_name,
                        query_vector=query_emb,
                        limit=top_k,
                    )
                    for point in resp:
                        results.append({
                            "id": point.id,
                            "text": point.payload.get("text", ""),
                            "metadata": {k: v for k, v in point.payload.items() if k != "text"},
                            "score": round(point.score, 4),
                        })
            except Exception as e:
                logger.warning(f"Qdrant search failed: {e}")
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

    async def _embed_query(self, query):
        try:
            from ..rag.embeddings import get_embedding_generator
            gen = get_embedding_generator()
            return await gen.embed_query(query)
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return None

    async def delete(self, ids):
        client = _get_qdrant()
        # 统一转换为 UUID
        ids = [self._to_uuid(pid) for pid in ids]
        if client is not None:
            try:
                from qdrant_client.models import PointIdsList
                client.delete(collection_name=self.collection_name, points_selector=PointIdsList(points=ids))
                return
            except Exception:
                pass
        self._fallback_store = [d for d in self._fallback_store if d["id"] not in ids]

    @property
    def count(self):
        client = _get_qdrant()
        if client is not None:
            try:
                info = client.get_collection(self.collection_name)
                return info.points_count
            except Exception:
                pass
        return len(self._fallback_store)


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
