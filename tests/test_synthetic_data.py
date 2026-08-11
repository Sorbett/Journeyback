from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_ROOT = PROJECT_ROOT / "data" / "synthetic"
KB_ROOT = PROJECT_ROOT / "data" / "knowledge_base"


class SyntheticDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = [
            json.loads(line)
            for line in (SYNTHETIC_ROOT / "journeyback_cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cls.quality = json.loads((SYNTHETIC_ROOT / "quality_report.json").read_text(encoding="utf-8"))
        cls.framework = json.loads((SYNTHETIC_ROOT / "evaluation_framework.json").read_text(encoding="utf-8"))

    def test_exact_case_and_split_allocation(self) -> None:
        self.assertEqual(600, len(self.cases))
        self.assertEqual(
            {"development": 360, "validation": 120, "test": 120},
            dict(Counter(case["split"] for case in self.cases)),
        )

    def test_exact_scenario_allocation(self) -> None:
        self.assertEqual(
            {
                "eligible_complete": 180,
                "ineligible_rule": 150,
                "insufficient_evidence": 120,
                "boundary_manual_review": 90,
                "unsupported_or_product_unknown": 60,
            },
            dict(Counter(case["scenario_class"] for case in self.cases)),
        )

    def test_safety_contract(self) -> None:
        self.assertTrue(all(case["synthetic"] is True for case in self.cases))
        self.assertTrue(all(case["human_review_required"] is True for case in self.cases))
        self.assertTrue(all(case["expected_payout_sgd"] is None for case in self.cases))

    def test_all_references_exist_in_knowledge_base(self) -> None:
        chunks = [
            json.loads(line)
            for line in (KB_ROOT / "rag" / "knowledge_base.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        chunk_ids = {chunk["chunk_id"] for chunk in chunks}
        source_ids = {
            source["source_id"]
            for source in json.loads((KB_ROOT / "normalized" / "sources.json").read_text(encoding="utf-8"))
        }
        self.assertTrue(all(set(case["expected_chunk_ids"]) <= chunk_ids for case in self.cases))
        self.assertTrue(all(set(case["expected_source_ids"]) <= source_ids for case in self.cases))

    def test_content_hashes_are_valid(self) -> None:
        for case in self.cases:
            expected_hash = case["content_hash"]
            unhashed = {key: value for key, value in case.items() if key != "content_hash"}
            payload = json.dumps(unhashed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.assertEqual(expected_hash, hashlib.sha256(payload.encode("utf-8")).hexdigest())

    def test_evaluation_weights_total_100(self) -> None:
        self.assertEqual(100, sum(component["weight"] for component in self.framework["components"]))
        self.assertTrue(self.quality["all_checks_passed"])


if __name__ == "__main__":
    unittest.main()
