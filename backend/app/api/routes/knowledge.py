"""
知识库管理路由 v4.0 — 混合检索 + RAG 问答 + 文档摄入
"""
from fastapi import APIRouter, Query, UploadFile, File
from pydantic import BaseModel
from loguru import logger

from ...memory.vector_store import get_vector_store, _get_qdrant
from ...rag.qa_chain import get_rag_chain
from ...rag.retriever import get_retriever

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


class IngestRequest(BaseModel):
    text: str
    source: str = ""
    tags: str = ""


class RAGQuery(BaseModel):
    question: str
    enable_reflection: bool = False


@router.get("/stats")
async def kb_stats():
    """知识库统计"""
    vs = get_vector_store()
    count = 0
    backend = "unknown"

    try:
        collection_info = vs.collection
        if collection_info:
            count = collection_info.points_count
            backend = "Qdrant"
        elif hasattr(vs, "_fallback_store"):
            count = len(vs._fallback_store)
            backend = "memory"
    except Exception:
        pass

    return {
        "collection": vs.collection_name,
        "document_count": count,
        "backend": backend,
        "tech": "BGE-M3 + Hybrid (Dense+Sparse+RRF) + BGE-Reranker",
    }


@router.get("/list")
async def kb_list(limit: int = Query(50, ge=1, le=200)):
    """列出知识库所有文档"""
    vs = get_vector_store()
    docs = []

    try:
        client = _get_qdrant()
        if client is not None:
            points, _ = client.scroll(
                collection_name=vs.collection_name,
                limit=limit,
                with_payload=True,
            )
            for i, point in enumerate(points):
                payload = point.payload or {}
                text = payload.get("text", "")
                meta = {k: v for k, v in payload.items() if k != "text"}
                docs.append({
                    "index": i + 1,
                    "id": str(point.id),
                    "content_preview": (text[:150] + "...") if len(text) > 150 else text,
                    "content_length": len(text),
                    "metadata": meta,
                })
    except Exception:
        pass

    if not docs and hasattr(vs, "_fallback_store"):
        for i, doc in enumerate(vs._fallback_store[:limit]):
            docs.append({
                "index": i + 1,
                "id": doc.get("id", ""),
                "content_preview": (doc.get("text", "")[:150] + "...") if len(doc.get("text", "")) > 150 else doc.get("text", ""),
                "content_length": len(doc.get("text", "")),
                "metadata": doc.get("metadata", {}),
            })

    return {"total": len(docs), "documents": docs}


@router.post("/ingest")
async def kb_ingest(req: IngestRequest):
    """导入文档到知识库（语义分块 + BGE-M3 向量化）"""
    chain = get_rag_chain()
    result = await chain.ingest_document(
        text=req.text,
        source=req.source or "manual_ingest",
    )
    logger.info(f"Ingested {result.get('ingested', 0)} chunks")
    return {"status": "ok", **result}


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB limit

@router.post("/ingest/file")
async def kb_ingest_file(file: UploadFile = File(...)):
    """上传文件到知识库 (最大 10MB)"""
    import tempfile
    import os

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        return {"error": f"文件过大，最大允许 {MAX_UPLOAD_SIZE // (1024*1024)}MB"}

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=os.path.splitext(file.filename or "doc.txt")[1]
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        chain = get_rag_chain()
        result = await chain.ingest_file(tmp_path, source=file.filename or "upload")
        return {"status": "ok", "filename": file.filename, **result}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.delete("/clear")
async def kb_clear():
    """清空知识库"""
    vs = get_vector_store()
    try:
        client = _get_qdrant()
        if client is not None:
            client.delete_collection(vs.collection_name)
            # 重新创建空 collection
            from qdrant_client.models import Distance, VectorParams
            from ..config import settings
            client.create_collection(
                collection_name=vs.collection_name,
                vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
            )
            return {"status": "cleared", "backend": "Qdrant"}
    except Exception:
        pass

    if hasattr(vs, "_fallback_store"):
        vs._fallback_store = []
        return {"status": "cleared", "backend": "memory"}

    return {"status": "error", "message": "Clear failed"}


@router.get("/search")
async def kb_search(
    q: str = Query(..., description="搜索关键词"),
    top_k: int = Query(5, ge=1, le=20),
    use_llm: bool = Query(False, description="是否用 LLM 生成回答"),
):
    """混合检索知识库（Dense+Sparse+RRF+Rerank）

    默认只返回文档片段。use_llm=true 时调用 LLM 生成RAG回答，
    如果知识库中没有相关内容会诚实告知。
    """
    if use_llm:
        chain = get_rag_chain()
        result = await chain.query(question=q)
        return result

    retriever = get_retriever()
    results = await retriever.retrieve(q)
    return {
        "query": q,
        "found": len(results) > 0,
        "hint": "无相关结果" if not results else None,
        "results": [
            {
                "text": r.get("text", "")[:300],
                "score": r.get("final_score", r.get("rrf_score", 0)),
                "dense_rank": r.get("dense_rank", "N/A"),
                "bm25_rank": r.get("bm25_rank", "N/A"),
                "rerank_score": r.get("rerank_score"),
                "metadata": r.get("metadata", {}),
            }
            for r in results[:top_k]
        ],
    }


@router.post("/rag")
async def rag_query(req: RAGQuery):
    """RAG 问答（检索增强生成，真实 LLM 调用）"""
    chain = get_rag_chain()
    result = await chain.query(
        question=req.question,
        enable_reflection=req.enable_reflection,
    )
    return result


@router.get("/rag/stream")
async def rag_query_stream(q: str = Query(...)):
    """流式 RAG 问答"""
    from fastapi.responses import StreamingResponse
    import json

    async def generate():
        chain = get_rag_chain()
        async for chunk in chain.query_stream(q):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
