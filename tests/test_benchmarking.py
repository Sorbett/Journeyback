from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.benchmarking import (  # noqa: E402
    BM25Ranker,
    evaluate_ranker,
    load_holdout,
    reciprocal_rank_fusion,
)
from journeyback.knowledge_base import KnowledgeBase  # noqa: E402


class RetrievalBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_holdout(
            PROJECT_ROOT / "data" / "evaluation" / "retrieval_holdout.jsonl"
        )
        cls.knowledge_base = KnowledgeBase.load()

    def test_holdout_is_separate_and_references_real_chunks(self) -> None:
        self.assertEqual(22, len(self.rows))
        chunk_ids = {
            chunk["chunk_id"] for chunk in self.knowledge_base.chunks
        }
        for row in self.rows:
            self.assertTrue(set(row["expected_chunk_ids"]).issubset(chunk_ids))
            self.assertTrue(row["label_source"].startswith("manual_reading"))

    def test_bm25_ranks_specific_policy_language(self) -> None:
        ranker = BM25Ranker(self.knowledge_base.chunks)
        ranked = ranker.rank(
            "My Travel Insurance six-hour block written operator confirmation",
            top_k=5,
        )
        self.assertIn("POL-SG-MY-TRAVEL-DELAY", ranked)

    def test_metrics_use_ranked_ground_truth(self) -> None:
        rows = [{
            "query_id": "Q1",
            "query": "query",
            "locale": "en-SG",
            "category": "test",
            "expected_chunk_ids": ["A"],
        }]
        report = evaluate_ranker(rows, lambda _query, _top_k: ["B", "A", "C"])
        self.assertEqual(1.0, report["metrics"]["hit_rate_at_5"])
        self.assertEqual(0.5, report["metrics"]["mrr_at_10"])

    def test_rank_fusion_rewards_results_supported_by_both_systems(self) -> None:
        fused = reciprocal_rank_fusion([["A", "B", "C"], ["B", "A", "D"]])
        self.assertEqual({"A", "B"}, set(fused[:2]))


if __name__ == "__main__":
    unittest.main()
