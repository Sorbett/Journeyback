from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_product import build_product_report  # noqa: E402


class ProductEvaluationTests(unittest.TestCase):
    def test_product_outcomes_precede_algorithm_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = build_product_report(output)
            html = (output / "report.html").read_text(encoding="utf-8")
            persisted = json.loads((output / "metrics.json").read_text(encoding="utf-8"))

        self.assertIsNone(report["product_value_score"])
        self.assertEqual("baseline_study_required", persisted["status"])
        self.assertEqual(5, len(report["product_scorecard"]))
        self.assertLess(
            html.index("Product outcomes come first"),
            html.index("Algorithm evidence · supporting layer"),
        )
        self.assertIn("PRODUCT VALUE SCORE · NOT YET CLAIMED", html)
        self.assertIn("First-pass evidence readiness", html)
