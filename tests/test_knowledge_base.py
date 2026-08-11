from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.knowledge_base import KnowledgeBase  # noqa: E402


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kb = KnowledgeBase.load()

    def test_expected_corpus_size(self) -> None:
        self.assertEqual(14, len(self.kb.sources))
        self.assertEqual(107, len(self.kb.chunks))

    def test_formal_policy_filter(self) -> None:
        policies = self.kb.filter_chunks(document_type="formal_policy_wording")
        self.assertEqual(22, len(policies))
        self.assertTrue(all(chunk["product_code"] for chunk in policies))

    def test_singapore_market_filter(self) -> None:
        self.assertEqual(107, len(self.kb.filter_chunks(market="SG")))

    def test_quality_checks_passed(self) -> None:
        self.assertTrue(self.kb.summary()["quality_checks_passed"])


if __name__ == "__main__":
    unittest.main()

