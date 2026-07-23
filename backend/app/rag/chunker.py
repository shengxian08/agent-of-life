"""
文档分块器 v4.0 — 语义分块 + 段落层次感知
支持三种策略：Semantic (LLM/Embedding-based) + Recursive + Sentence
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger


class DocumentChunker:
    """智能文档分块器 — 优先语义分块，降级递归分块"""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        strategy: str = "semantic",
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy

    def split_text(self, text: str) -> list[str]:
        """分块主入口 — 自动选择最优策略"""
        if not text or not text.strip():
            return []

        if self.strategy == "semantic":
            return self._semantic_split(text)

        return self._recursive_split(text)

    def _semantic_split(self, text: str) -> list[str]:
        """语义分块 — 基于 Embedding 相似度断点

        原理：计算相邻句子的余弦相似度，在相似度骤降处切断
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return [text.strip()] if text.strip() else []

        try:
            from .embeddings import get_embedding_generator
            embedder = get_embedding_generator()
            embeddings = embedder.embed_sync(sentences)

            if not embeddings or len(embeddings) != len(sentences):
                raise ValueError("Embedding failed")

            # 计算相邻句子相似度
            import numpy as np

            similarities = []
            for i in range(len(embeddings) - 1):
                a, b = np.array(embeddings[i]), np.array(embeddings[i + 1])
                a_norm = np.linalg.norm(a)
                b_norm = np.linalg.norm(b)
                if a_norm == 0 or b_norm == 0:
                    sim = 0.0
                else:
                    sim = float(np.dot(a, b) / (a_norm * b_norm))
                similarities.append(sim)

            if not similarities:
                return [text.strip()]

            # 自适应阈值：均值 - 1 个标准差
            sim_array = np.array(similarities)
            threshold = float(sim_array.mean() - sim_array.std())

            # 在低相似度处断点
            breakpoints = [
                i + 1 for i, sim in enumerate(similarities) if sim < threshold
            ]

            # 合并句子为 chunks
            chunks = self._merge_sentences_to_chunks(sentences, breakpoints)

        except Exception as e:
            logger.warning(f"Semantic chunking failed ({e}), falling back to recursive")
            return self._recursive_split(text)

        if not chunks:
            return [text.strip()]
        return chunks

    def _recursive_split(self, text: str) -> list[str]:
        """递归分块 — 按段落 → 句子 → 字符 逐级降维"""
        separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " "]
        return self._split_recursive(text, separators)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            # 最后手段：按长度强制切
            return [
                text[i:i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size - self.chunk_overlap)
            ]

        sep = separators[0]
        remaining_seps = separators[1:]

        if sep == " ":
            parts = text.split(sep)
        else:
            # 保留分隔符
            parts = re.split(f"(?<={re.escape(sep)})", text)

        chunks = []
        current = ""

        for part in parts:
            if len(current) + len(part) <= self.chunk_size:
                current += part
            else:
                if current.strip():
                    chunks.append(current.strip())
                # 如果单段超过 chunk_size，用下一级分隔符继续切
                if len(part) > self.chunk_size:
                    sub_chunks = self._split_recursive(part, remaining_seps)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """中文/英文分句"""
        # 正则分句：保留分隔符在句尾
        pattern = r'(?<=[。！？.!?\n])\s*'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _merge_sentences_to_chunks(
        self, sentences: list[str], breakpoints: list[int]
    ) -> list[str]:
        """将句子按断点合并为 chunks，控制 chunk_size"""
        chunks = []
        current = ""
        for i, sent in enumerate(sentences):
            if len(current) + len(sent) <= self.chunk_size:
                current += sent + " "
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = sent + " "

            # 断点处强制换 chunk
            if i + 1 in breakpoints and current.strip():
                chunks.append(current.strip())
                current = ""

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def split_documents(
        self, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """批量分块，保留元数据"""
        result = []
        for doc in documents:
            text = doc.get("text", "") or doc.get("content", "")
            chunks = self.split_text(text)
            for i, chunk in enumerate(chunks):
                result.append({
                    "text": chunk,
                    "metadata": {
                        **(doc.get("metadata", {})),
                        "chunk_index": i,
                        "chunk_count": len(chunks),
                    },
                })
        return result
