"""
RAG 问答链 v4.0 — 真正的 LLM 驱动的检索增强生成
支持：Self-RAG 自省、信源引用、流式输出
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, AsyncGenerator

from loguru import logger

from ..config import settings


class RAGChain:
    """RAG 问答引擎 — 检索 → 重排 → LLM 生成 → 自省"""

    RAG_SYSTEM_PROMPT = """你是智能家务助手。严格基于下方提供的【参考信息】回答问题。

规则：
1. 如果参考信息足够，直接回答并引用 [文档编号]
2. 如果参考信息不足，诚实说明"根据现有知识库无法确定"，不要编造
3. 用口语化中文，层次分明，关键信息用换行分隔
4. 回答末尾可以附上"💡 建议"（仅当信息充分时）"""

    FALLBACK_SYSTEM_PROMPT = """你是智能家务助手。知识库中没有找到与用户问题直接相关的资料。

请用你的知识直接回答用户的问题。规则：
1. 用口语化中文，像管家聊天一样自然
2. 如果涉及菜谱做法，给出详细食材和步骤
3. 如果涉及家电维修，优先建议安全操作和联系专业师傅
4. 如果不确定，诚实告知并给出建议方向
5. 回答末尾标注「💡 提示：该回答基于通用知识，如需精确信息建议补充相关知识库」"""

    def __init__(self):
        from .retriever import get_retriever
        self.retriever = get_retriever()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=settings.api_key,
                base_url=settings.openai_base_url,
                timeout=60.0,
                max_retries=2,
            )
        return self._client

    async def query(
        self,
        question: str,
        session_id: str = "",
        filters: dict | None = None,
        enable_reflection: bool = False,
    ) -> dict[str, Any]:
        """标准 RAG 查询（非流式）"""
        # 1. 检索
        context = await self.retriever.retrieve_context(question, filters)
        sources = await self.retriever.retrieve(question, filters)
        sources_count = len(sources)

        if not context:
            # ═══════════════════════════════════════════════
            # Fallback: 无检索结果 → LLM 直接回答
            # ═══════════════════════════════════════════════
            logger.info("RAG_FALLBACK: No context found, using LLM-only mode")
            try:
                resp = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": self.FALLBACK_SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                )
                answer = resp.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"Fallback LLM call failed: {e}")
                answer = "抱歉，知识库中暂无相关内容，AI 服务也暂时不可用，请稍后重试。"

            return {
                "question": question,
                "answer": answer,
                "context": "",
                "sources_count": 0,
                "sources": [],
                "fallback": True,
            }

        # 2. LLM 生成
        prompt = self._build_prompt(question, context)

        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": self.RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            answer = resp.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM call failed in RAG: {e}")
            answer = f"RAG 生成失败：{str(e)}。检索到 {sources_count} 条相关资料，请稍后重试。"

        # 3. 可选的答案自省 (Self-RAG)
        is_reliable = None
        if enable_reflection and sources_count > 0:
            is_reliable = await self._reflect(question, context, answer)

        return {
            "question": question,
            "answer": answer,
            "context": context[:2000],
            "sources_count": sources_count,
            "sources": [
                {
                    "text": s.get("text", "")[:300],
                    "score": s.get("final_score", s.get("rrf_score", 0)),
                    "metadata": s.get("metadata", {}),
                }
                for s in sources[:5]
            ],
            "is_reliable": is_reliable,
        }

    async def query_stream(
        self, question: str, session_id: str = ""
    ) -> AsyncGenerator[str, None]:
        """流式 RAG 查询"""
        context = await self.retriever.retrieve_context(question)
        if not context:
            yield "抱歉，知识库中没有找到相关信息。"
            return

        prompt = self._build_prompt(question, context)

        try:
            stream = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": self.RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Stream RAG failed: {e}")
            yield f"\n\n[生成中断: {str(e)}]"

    async def _reflect(
        self, question: str, context: str, answer: str
    ) -> bool:
        """Self-RAG 答案自省 — 验证答案是否有据可查"""
        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": "判断以下答案是否完全基于提供的参考信息。只回答 YES 或 NO。"
                }, {
                    "role": "user",
                    "content": f"参考信息:\n{context[:1500]}\n\n答案:\n{answer[:500]}\n\n答案完全基于参考信息吗？"
                }],
                temperature=0,
                max_tokens=10,
            )
            result = (resp.choices[0].message.content or "").strip().upper()
            return "YES" in result
        except Exception:
            return None

    def _build_prompt(self, question: str, context: str) -> str:
        return f"""参考信息：
{context}

问题：{question}

请用中文清晰回答，并在关键事实后标注引用来源如 [文档1]."""

    # ================================================================
    # 文档摄入
    # ================================================================

    async def ingest_document(
        self, text: str, metadata: dict | None = None, source: str = ""
    ) -> dict[str, Any]:
        """摄入文档到知识库（语义分块 + 向量化入库）"""
        from .chunker import DocumentChunker
        from .embeddings import get_embedding_generator

        chunker = DocumentChunker(strategy="semantic")
        chunks = chunker.split_text(text)

        if not chunks:
            return {"ingested": 0, "chunks": [], "error": "No valid text to ingest"}

        # 生成 Embedding 并存储
        embedder = get_embedding_generator()
        embed_result = await embedder.embed_documents(chunks)
        dense_vecs = embed_result.get("dense_vecs", [])

        # 构建 ID
        meta = metadata or {}
        if source:
            meta["source"] = source
        meta["ingested_at"] = datetime.now().isoformat()

        ids = [
            f"rag_{hashlib.md5(c.encode()).hexdigest()[:12]}"
            for c in chunks
        ]

        # 存入 ChromaDB（带上预计算的 embedding）
        embeddings_list = dense_vecs if dense_vecs else None
        await self.retriever.vector_store.add(
            texts=chunks,
            metadatas=[meta for _ in chunks],
            ids=ids,
            embeddings=embeddings_list,
        )

        logger.info(f"Ingested {len(chunks)} chunks from '{source or 'unknown'}'")

        return {
            "ingested": len(chunks),
            "chunks": chunks[:3],
            "chunk_ids": ids,
            "source": source,
        }

    async def ingest_file(self, file_path: str, source: str = "") -> dict[str, Any]:
        """摄入文件（支持 PDF/DOCX/TXT/MD）"""
        import os

        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        ext = os.path.splitext(file_path)[1].lower()
        text = ""

        if ext == ".txt" or ext == ".md":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    text = "\n\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
            except ImportError:
                return {"error": "pdfplumber not installed"}
        elif ext == ".docx":
            try:
                from docx import Document
                doc = Document(file_path)
                text = "\n\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                return {"error": "python-docx not installed"}
        else:
            return {"error": f"Unsupported file type: {ext}"}

        if not text.strip():
            return {"ingested": 0, "error": "文件内容为空，可能是扫描版PDF（图片），请先用OCR转文字后再上传"}

        # 中文占比检测：低于 30% 可能是乱码或非中文文档
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        total_chars = len(text.replace('\n', '').replace(' ', ''))
        cn_ratio = chinese_chars / max(total_chars, 1)
        if cn_ratio < 0.1 and total_chars > 100:
            return {
                "ingested": 0,
                "error": f"中文占比仅 {cn_ratio:.0%}，文档可能是乱码。扫描版PDF请用OCR工具（如微信截图识字）提取文字后再上传。",
                "preview": text[:200],
            }

        return await self.ingest_document(
            text, source=source or os.path.basename(file_path)
        )


# 全局单例
_rag_chain: RAGChain | None = None


def get_rag_chain() -> RAGChain:
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = RAGChain()
    return _rag_chain
