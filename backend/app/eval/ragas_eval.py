"""
RAG 评估引擎 — 跑测试集 -> LLM Judge 四项指标 -> 出报告
用法: python -m app.eval.ragas_eval
"""
import sys
import os
import json
import asyncio
import re
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from loguru import logger
from app.rag.qa_chain import get_rag_chain
from app.rag.retriever import get_retriever
from app.eval.test_dataset import TEST_SAMPLES, SCENE_COUNTS


class RAGEvaluator:

    def __init__(self):
        self.rag_chain = get_rag_chain()
        self.retriever = get_retriever()
        self.results: list[dict] = []

    async def run_all(self) -> dict:
        print(f"\n{'='*60}")
        print(f"  RAG System Eval - {len(TEST_SAMPLES)} samples")
        print(f"{'='*60}\n")

        for i, sample in enumerate(TEST_SAMPLES):
            question = sample["question"]
            ground_truth = sample["ground_truth"]
            print(f"[{i+1}/{len(TEST_SAMPLES)}] {question}")

            # 1. 检索
            docs = await self.retriever.retrieve(question)
            contexts = [d.get("text", "") for d in docs]

            # 2. RAG 生成
            result = await self.rag_chain.query(question=question)
            answer = result.get("answer", "")

            # 3. 记录
            self.results.append({
                "question": question,
                "answer": answer,
                "ground_truth": ground_truth,
                "contexts": contexts,
                "sources_count": result.get("sources_count", 0),
                "is_fallback": result.get("fallback", False),
            })

            ctx_preview = (contexts[0][:80] + "...") if contexts else "(none)"
            safe_answer = answer.encode("ascii", errors="replace").decode("ascii")[:80]
            print(f"    retrieved: {len(contexts)} | answer: {safe_answer}...")
            print()

        scores = await self._compute_scores()
        report = self._build_report(scores)
        self._print_report(report)
        return report

    async def _compute_scores(self) -> dict:
        ragas_scores = await self._llm_judge_scores()
        custom_scores = self._custom_metrics()
        return {**ragas_scores, **custom_scores}

    async def _judge_one(self, system_prompt: str, user_prompt: str) -> float:
        """让 LLM 当评委，返回 0~1 分数"""
        from openai import AsyncOpenAI
        from app.config import settings
        client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.openai_base_url)
        try:
            resp = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=50,
            )
            text = (resp.choices[0].message.content or "0.5").strip()
            nums = re.findall(r"([\d.]+)", text)
            if nums:
                score = float(nums[0])
                return max(0.0, min(1.0, score))
            return 0.5
        except Exception as e:
            logger.warning(f"LLM judge failed: {e}")
            return 0.5

    async def _llm_judge_scores(self) -> dict:
        """基于 LLM Judge 的四项指标（替代 RAGAS 库）"""
        print("\n  [LLM Judge] 正在评估 11 个样本 x 4 项指标...")

        faith_scores = []
        relevancy_scores = []
        precision_scores = []
        recall_scores = []

        for i, r in enumerate(self.results):
            question = r["question"]
            answer = r["answer"]
            ground_truth = r["ground_truth"]
            contexts = r["contexts"]
            ctx_text = "\n---\n".join(contexts[:3]) if contexts else "(无)"

            print(f"    judging [{i+1}/11] {question[:30]}...")

            results = await asyncio.gather(
                self._judge_one(
                    "你是 RAG 评估专家。只输出 0~1 的数字。",
                    f"上下文:\n{ctx_text[:2000]}\n\n答案:\n{answer[:1000]}\n\n"
                    "答案中的每个事实是否都来自上下文？没有编造？\n"
                    "1.0=完全忠实 0.5=部分编造 0.0=大量编造\n只输出数字:"
                ),
                self._judge_one(
                    "你是 RAG 评估专家。只输出 0~1 的数字。",
                    f"问题: {question}\n答案: {answer[:1000]}\n\n"
                    "答案是否直接、完整地回应用户的问题？\n"
                    "1.0=完美切题 0.5=部分偏题 0.0=完全不相关\n只输出数字:"
                ),
                self._judge_one(
                    "你是 RAG 评估专家。只输出 0~1 的数字。",
                    f"问题: {question}\n检索文档:\n{ctx_text[:2000]}\n\n"
                    "检索到的文档与问题相关吗？\n"
                    "1.0=高度相关 0.5=部分相关 0.0=完全无关\n只输出数字:"
                ),
                self._judge_one(
                    "你是 RAG 评估专家。只输出 0~1 的数字。",
                    f"标准答案应包含: {ground_truth[:1000]}\n检索文档:\n{ctx_text[:2000]}\n\n"
                    "检索文档覆盖了标准答案中的关键信息吗？\n"
                    "1.0=完全覆盖 0.5=部分覆盖 0.0=未覆盖\n只输出数字:"
                ),
                return_exceptions=True,
            )

            faith_scores.append(results[0] if not isinstance(results[0], Exception) else 0.5)
            relevancy_scores.append(results[1] if not isinstance(results[1], Exception) else 0.5)
            precision_scores.append(results[2] if not isinstance(results[2], Exception) else 0.5)
            recall_scores.append(results[3] if not isinstance(results[3], Exception) else 0.5)

        def avg(lst):
            return round(sum(lst) / max(len(lst), 1), 4)

        return {
            "faithfulness": avg(faith_scores),
            "answer_relevancy": avg(relevancy_scores),
            "context_precision": avg(precision_scores),
            "context_recall": avg(recall_scores),
        }

    def _custom_metrics(self) -> dict:
        total = max(len(self.results), 1)
        hit_count = sum(1 for r in self.results if len(r["contexts"]) > 0)
        non_fb = sum(1 for r in self.results if not r["is_fallback"])
        avg_ctx = sum(len(r["contexts"]) for r in self.results) / total
        return {
            "retrieval_hit_rate": round(hit_count / total, 4),
            "avg_contexts_per_query": round(avg_ctx, 1),
            "non_fallback_rate": round(non_fb / total, 4),
        }

    def _build_report(self, scores: dict) -> dict:
        per_sample = []
        for r in self.results:
            per_sample.append({
                "question": r["question"][:50],
                "answer_preview": r["answer"][:100],
                "sources_count": r["sources_count"],
                "is_fallback": r["is_fallback"],
            })
        return {
            "timestamp": datetime.now().isoformat(),
            "total_samples": len(self.results),
            "scores": scores,
            "scene_breakdown": self._scene_breakdown(),
            "per_sample": per_sample,
        }

    def _scene_breakdown(self) -> dict:
        breakdown = {}
        idx = 0
        for scene, count in SCENE_COUNTS.items():
            batch = self.results[idx:idx+count]
            idx += count
            hit = sum(1 for r in batch if len(r["contexts"]) > 0)
            breakdown[scene] = {
                "samples": len(batch),
                "retrieval_hit": hit,
                "hit_rate": round(hit / max(len(batch), 1) * 100, 1),
            }
        return breakdown

    def _print_report(self, report: dict):
        scores = report["scores"]
        print(f"{'='*60}")
        print(f"  EVAL REPORT")
        print(f"{'='*60}")
        print(f"  Samples: {report['total_samples']}")
        print(f"  Time: {report['timestamp']}")
        print(f"{'-'*60}")

        ragas_keys = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
        if any(k in scores for k in ragas_keys):
            print(f"  [RAGAS Metrics]")
            labels = {
                "faithfulness": "Faithfulness",
                "answer_relevancy": "Answer Relevance",
                "context_precision": "Context Precision",
                "context_recall": "Context Recall",
            }
            for k in ragas_keys:
                if k in scores and scores[k] is not None:
                    bar = "#" * int(scores[k] * 20) + "-" * (20 - int(scores[k] * 20))
                    print(f"    {labels.get(k, k):20s}: {bar} {scores[k]:.4f}")

        custom_keys = ["retrieval_hit_rate", "avg_contexts_per_query", "non_fallback_rate"]
        if any(k in scores for k in custom_keys):
            print(f"  [Custom Metrics]")
            labels = {
                "retrieval_hit_rate": "Retrieval Hit Rate",
                "avg_contexts_per_query": "Avg Contexts/Query",
                "non_fallback_rate": "Knowledge Base Hit",
            }
            for k in custom_keys:
                if k in scores and scores[k] is not None:
                    print(f"    {labels.get(k, k):20s}: {scores[k]}")

        print(f"\n  [Scene Breakdown]")
        for scene, info in report["scene_breakdown"].items():
            bar = "#" * int(info["hit_rate"] / 10) + "-" * (10 - int(info["hit_rate"] / 10))
            print(f"    {scene:10s}: {bar} {info['hit_rate']}% ({info['retrieval_hit']}/{info['samples']})")

        print(f"{'='*60}\n")

        report_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "eval_report.json"
        )
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Report saved: {report_path}")


async def main():
    evaluator = RAGEvaluator()
    await evaluator.run_all()


if __name__ == "__main__":
    asyncio.run(main())
