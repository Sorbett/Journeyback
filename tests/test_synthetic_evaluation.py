from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_synthetic_cases import evaluate_cases  # noqa: E402


class SyntheticEvaluationTests(unittest.TestCase):
    def test_visual_evaluation_materialises_all_case_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            summary = evaluate_cases(output_dir)
            rows = [json.loads(line) for line in (output_dir / "results.jsonl").read_text().splitlines()]
            report = (output_dir / "report.html").read_text(encoding="utf-8")

        self.assertEqual("completed", summary["status"])
        self.assertEqual(600, len(rows))
        self.assertEqual(600, summary["materialised_results"])
        self.assertIn("What 600 synthetic journeys tell us", report)
        self.assertIn("need explanation or triage", report)
        self.assertTrue(all(row["result_status"] == "expected_result_materialised" for row in rows))


if __name__ == "__main__":
    unittest.main()
