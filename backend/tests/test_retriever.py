"""
测试 RAG 检索流水线 — 单元测试，不需要外部服务
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestRRFFusion:
    """RRF 融合算法测试 — 纯逻辑，不依赖外部服务"""

    def test_rrf_empty_inputs(self):
        """两个空输入 → 返回空列表"""
        from app.rag.retriever import HybridRetriever
        r = HybridRetriever()
        result = r._rrf_fusion({}, [])
        assert result == []

    def test_rrf_dense_only(self):
        """只有 Dense 结果 → 正确计算 RRF 分数"""
        from app.rag.retriever import HybridRetriever
        r = HybridRetriever()
        dense = {
            "doc1": {"dense_score": 0.9, "text": "test1"},
            "doc2": {"dense_score": 0.7, "text": "test2"},
        }
        result = r._rrf_fusion(dense, [])
        assert len(result) == 2
        # doc1 分数应高于 doc2（排名更靠前）
        assert result[0]["id"] == "doc1"
        assert result[0]["rrf_score"] > result[1]["rrf_score"]

    def test_rrf_both_sources(self):
        """Dense + BM25 双路融合 → 交集文档分数更高"""
        from app.rag.retriever import HybridRetriever
        r = HybridRetriever()
        dense = {
            "shared": {"dense_score": 0.8, "text": "both rank high"},
            "dense_only": {"dense_score": 0.5, "text": "dense only"},
        }
        bm25 = [
            {"id": "shared", "bm25_score": 0.9, "text": "both rank high"},
            {"id": "bm25_only", "bm25_score": 0.6, "text": "bm25 only"},
        ]
        result = r._rrf_fusion(dense, bm25)
        assert len(result) == 3
        # shared 文档在两个列表中都有 → 应该排第一
        assert result[0]["id"] == "shared"

    def test_rrf_single_document(self):
        """单个文档 → 正确计算"""
        from app.rag.retriever import HybridRetriever
        r = HybridRetriever()
        result = r._rrf_fusion({"only": {"dense_score": 0.9}}, [])
        assert len(result) == 1
        assert result[0]["rrf_score"] > 0


class TestDocumentChunker:
    """文档分块器测试"""

    def test_empty_text(self):
        from app.rag.chunker import DocumentChunker
        c = DocumentChunker(strategy="recursive")
        assert c.split_text("") == []
        assert c.split_text("   ") == []

    def test_short_text_single_chunk(self):
        from app.rag.chunker import DocumentChunker
        c = DocumentChunker(strategy="recursive", chunk_size=500)
        result = c.split_text("这是一段短文本")
        assert len(result) == 1

    def test_paragraph_split(self):
        from app.rag.chunker import DocumentChunker
        c = DocumentChunker(strategy="recursive", chunk_size=20)
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        result = c.split_text(text)
        assert len(result) >= 2

    def test_chinese_sentence_split(self):
        from app.rag.chunker import DocumentChunker
        c = DocumentChunker(strategy="recursive", chunk_size=100)
        text = "今天天气很好。我们去买菜吧！买什么好呢？"
        result = c.split_text(text)
        assert len(result) >= 1  # 至少能正常分


class TestQueryRewrite:
    """查询改写测试（不调 LLM 时验证兜底逻辑）"""

    def test_rewrite_returns_original(self):
        """即使 LLM 不可用，原始查询也必须保留"""
        from app.rag.retriever import HybridRetriever
        r = HybridRetriever()
        # 这个方法会尝试调 LLM，失败时兜底返回 [原始查询]
        import asyncio
        queries = asyncio.run(r._rewrite_query("红烧肉怎么做"))
        assert "红烧肉怎么做" in queries
        assert len(queries) >= 1
