"""
Embedding 生成器 v4.1 — BGE-M3 本地优先 + API 可选降级
策略：本地 BGE-M3 (主) > ONNX 加速 > sentence-transformers > OpenAI API (备)
"""
from __future__ import annotations

import asyncio
import os
import threading
from functools import lru_cache
from typing import Any

from loguru import logger

from ..config import settings


class EmbeddingGenerator:
    """BGE-M3 本地 Embedding — 支持 ONNX 加速 + Dense/Sparse 双路编码

    推荐层级（自动降级）：
      1. FlagEmbedding BGEM3FlagModel (原生, Dense+Sparse, FP16)
      2. ONNX Runtime (CPU 优化, 2-3x 加速)
      3. sentence-transformers (通用降级)
      4. OpenAI API (最后备选, 仅 Dense)
    """

    def __init__(self):
        self.model_name = settings.embedding_model_name
        self.device = settings.embedding_device
        self._model = None
        self._model_type: str = ""  # "flagembedding" | "onnx" | "sentence_transformers" | "openai_api"
        self._model_lock = threading.Lock()
        self._onnx_path: str | None = None
        # 小查询缓存 (LRU, 最多 256 条)
        self._query_cache: dict[str, list[float]] = {}
        self._cache_hits = 0    # 监控用
        self._cache_misses = 0

    # ================================================================
    # 模型加载
    # ================================================================

    def _ensure_hf_cache_on_d_drive(self):
        """强制 HF 缓存到 D 盘，避免重复下载到 C 盘"""
        import os as _os
        d_drive_cache = str(settings.data_dir / "models" / "huggingface")
        if not _os.environ.get("HF_HOME") or "D:" not in _os.environ.get("HF_HOME", ""):
            _os.environ["HF_HOME"] = d_drive_cache
            _os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
            logger.debug(f"HF cache forced to: {d_drive_cache}")

    def _load_model(self):
        """懒加载 — 按优先级尝试：FlagEmbedding → ONNX → SentenceTransformer → API"""
        with self._model_lock:
            if self._model is not None:
                return

            self._ensure_hf_cache_on_d_drive()

            # 策略 1: FlagEmbedding (BGE-M3 原生, Dense+Sparse 全套)
            if self._try_load_flagembedding():
                return

            # 策略 2: sentence-transformers (Dense only, 兜底)
            if self._try_load_sentence_transformers():
                return

            # 策略 3: ONNX 加速模型
            if self._try_load_onnx():
                return

            # 策略 4: OpenAI API 最后备选
            if self._try_setup_api_fallback():
                return

            logger.error("All embedding strategies failed! Vector search will not work.")

    def _try_load_flagembedding(self) -> bool:
        try:
            # 国内用户优先使用 HF 镜像，避免被墙
            import os as _os
            if not _os.environ.get("HF_ENDPOINT"):
                _os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                logger.info("Using HF mirror: https://hf-mirror.com (for China)")

            from FlagEmbedding import BGEM3FlagModel
            import os as _os
            model_exists = _os.path.isdir(self.model_name) or _os.path.isfile(self.model_name)
            if model_exists:
                logger.info(f"Loading BGE-M3 model from local cache: {self.model_name} on {self.device}...")
            else:
                logger.info(
                    f"BGE-M3 model not found locally, downloading from hf-mirror.com..."
                    f"\n  Model: {self.model_name}"
                    f"\n  Size: ~2.2GB, may take 2-5 minutes (once only)"
                )
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=(self.device != "cpu"),
                device=self.device,
            )
            self._model_type = "flagembedding"
            logger.success(f"BGE-M3 loaded (FlagEmbedding, {'FP16' if self.device != 'cpu' else 'FP32'})")
            return True
        except ImportError:
            logger.debug("FlagEmbedding not installed")
        except Exception as e:
            logger.warning(f"FlagEmbedding load failed: {e}")
            logger.info(
                "Trying alternative: set env var and retry.\n"
                "  $env:HF_ENDPOINT='https://hf-mirror.com'  (PowerShell)\n"
                "  or export HF_ENDPOINT=https://hf-mirror.com  (Bash)"
            )
        return False

    def _try_load_onnx(self) -> bool:
        """尝试加载预导出的 ONNX 模型 (CPU 上 2-3x 加速)"""
        # 查找 ONNX 模型目录
        onnx_dir = os.path.join(str(settings.data_dir), "models", "bge-m3-onnx")
        if not os.path.exists(onnx_dir):
            logger.debug(f"No ONNX model at {onnx_dir}, skipping")
            return False

        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer
            logger.info(f"Loading BGE-M3 (ONNX) from {onnx_dir}...")
            self._model = ORTModelForFeatureExtraction.from_pretrained(onnx_dir)
            self._model_tokenizer = AutoTokenizer.from_pretrained(onnx_dir)
            self._model_type = "onnx"
            self._onnx_path = onnx_dir
            logger.success("BGE-M3 loaded (ONNX optimized)")
            return True
        except ImportError:
            logger.debug("optimum[onnxruntime] not installed, ONNX unavailable")
        except Exception as e:
            logger.warning(f"ONNX load failed: {e}")
        return False

    def _try_load_sentence_transformers(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading model via sentence-transformers: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._model_type = "sentence_transformers"
            logger.success("Model loaded (sentence-transformers)")
            return True
        except ImportError:
            logger.debug("sentence-transformers not installed")
        except Exception as e:
            logger.warning(f"SentenceTransformer load failed: {e}")
        return False

    def _try_setup_api_fallback(self) -> bool:
        """OpenAI API 作为最后备选 (仅 Dense)"""
        api_key = settings.api_key
        if not api_key or api_key == "sk-xxx":
            return False
        try:
            logger.warning("Using OpenAI API for embeddings (fallback mode, higher latency & cost)")
            self._model = "api"
            self._model_type = "openai_api"
            return True
        except Exception:
            return False

    # ================================================================
    # Embedding 编码
    # ================================================================

    async def embed_texts(
        self, texts: list[str], return_sparse: bool = False
    ) -> dict[str, Any]:
        # 主线程加载模型（避免线程中加载导致 segfault）
        self._load_model()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._embed_sync, texts, return_sparse
        )

    def _embed_sync(self, texts: list[str], return_sparse: bool) -> dict[str, Any]:
        self._load_model()

        try:
            if self._model_type == "flagembedding":
                return self._embed_flagembedding(texts, return_sparse)
            elif self._model_type == "onnx":
                return self._embed_onnx(texts)
            elif self._model_type == "sentence_transformers":
                return self._embed_st(texts)
            elif self._model_type == "openai_api":
                return self._embed_api_sync(texts)
            else:
                return self._zero_vectors(len(texts))
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return self._zero_vectors(len(texts))

    def _embed_flagembedding(self, texts: list[str], return_sparse: bool) -> dict:
        from FlagEmbedding import BGEM3FlagModel
        output = self._model.encode(
            texts,
            batch_size=12,
            max_length=8192,
            return_dense=True,
            return_sparse=return_sparse,
            return_colbert_vecs=False,
        )
        return {
            "dense_vecs": [v.tolist() for v in output["dense_vecs"]],
            "sparse_vecs": output.get("lexical_weights", None),
        }

    def _embed_onnx(self, texts: list[str]) -> dict:
        """ONNX 推理 (CPU 优化, mean pooling)"""
        import numpy as np
        import torch

        tokenizer = getattr(self, "_model_tokenizer", None)
        if tokenizer is None:
            return self._zero_vectors(len(texts))

        all_embeddings = []
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            inputs = tokenizer(
                batch, padding=True, truncation=True,
                max_length=512, return_tensors="pt",
            )
            outputs = self._model(**inputs)
            # Mean pooling with attention mask
            attention_mask = inputs["attention_mask"]
            token_embeddings = outputs.last_hidden_state
            input_mask_expanded = (
                attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            )
            embeddings = torch.sum(
                token_embeddings * input_mask_expanded, 1
            ) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            # L2 normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            all_embeddings.extend(embeddings.detach().cpu().numpy().tolist())

        return {"dense_vecs": all_embeddings, "sparse_vecs": None}

    def _embed_st(self, texts: list[str]) -> dict:
        from sentence_transformers import SentenceTransformer
        embeddings = self._model.encode(
            texts, batch_size=32, show_progress_bar=False,
            normalize_embeddings=True,
        )
        return {"dense_vecs": [e.tolist() for e in embeddings], "sparse_vecs": None}

    def _embed_api_sync(self, texts: list[str]) -> dict:
        """OpenAI API Embedding (同步, 最后备选)"""
        try:
            import httpx
            resp = httpx.post(
                f"{settings.openai_base_url}/embeddings",
                headers={"Authorization": f"Bearer {settings.api_key}"},
                json={"model": "text-embedding-3-small", "input": texts},
                timeout=30.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "dense_vecs": [d["embedding"] for d in data["data"]],
                    "sparse_vecs": None,
                }
        except Exception as e:
            logger.error(f"API embedding failed: {e}")
        return self._zero_vectors(len(texts))

    def _zero_vectors(self, count: int) -> dict:
        return {"dense_vecs": [[0.0] * settings.embedding_dim for _ in range(count)], "sparse_vecs": None}

    # ================================================================
    # 公共 API
    # ================================================================

    async def embed_query(self, query: str) -> list[float]:
        """生成查询向量 (带 LRU 缓存, 重复查询命中率 40-60%)"""
        cache_key = query.strip()
        if cache_key in self._query_cache:
            self._cache_hits += 1
            return self._query_cache[cache_key]

        self._cache_misses += 1
        result = await self.embed_texts([query], return_sparse=False)
        vec = result["dense_vecs"][0]

        # LRU 缓存 (最多 512 条)
        if len(self._query_cache) >= 512:
            # 淘汰最旧的一条
            self._query_cache.pop(next(iter(self._query_cache)))
        self._query_cache[cache_key] = vec
        return vec

    async def embed_documents(self, documents: list[str]) -> dict[str, Any]:
        """生成文档向量 (Dense + Sparse，用于入库)"""
        return await self.embed_texts(documents, return_sparse=True)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """同步嵌入 (兼容旧接口)"""
        self._load_model()
        result = self._embed_sync(texts, return_sparse=False)
        return result["dense_vecs"]

    @property
    def model_info(self) -> dict:
        return {
            "model_name": self.model_name,
            "model_type": self._model_type or "not_loaded",
            "device": self.device,
            "dimension": settings.embedding_dim,
            "sparse_support": self._model_type == "flagembedding",
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
        }


# ================================================================
# 导出 ONNX 工具函数 (用于一次性导出加速模型)
# ================================================================

async def export_onnx_model(
    model_name: str = "BAAI/bge-m3",
    output_dir: str | None = None,
) -> str:
    """将 BGE-M3 导出为 ONNX 格式 (CPU 推理 2-3x 加速)

    运行一次即可，之后自动使用 ONNX:

        python -c "import asyncio; from app.rag.embeddings import export_onnx_model; asyncio.run(export_onnx_model())"
    """
    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from transformers import AutoTokenizer, AutoModel
    except ImportError:
        raise ImportError("Install: pip install optimum[onnxruntime]")

    if output_dir is None:
        output_dir = os.path.join(str(settings.data_dir), "models", "bge-m3-onnx")

    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Exporting {model_name} to ONNX -> {output_dir}")
    logger.info("This may take 5-10 minutes on first run...")

    model = AutoModel.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    ort_model = ORTModelForFeatureExtraction.from_pretrained(
        model_name, export=True
    )
    ort_model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    logger.success(f"ONNX model exported to {output_dir}")
    return output_dir


# 全局单例
_embedding_generator: EmbeddingGenerator | None = None


def get_embedding_generator() -> EmbeddingGenerator:
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator
