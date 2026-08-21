from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.synthetic_demo import (  # noqa: E402
    dataset_insights,
    get_case,
    recovery_case_from_synthetic,
    synthetic_cases,
    trip_from_case,
)


class SyntheticDemoTests(unittest.TestCase):
    def test_all_generated_cases_are_available_to_the_demo(self) -> None:
        cases = synthetic_cases()
        self.assertEqual(600, len(cases))
        self.assertEqual(600, len({case["case_id"] for case in cases}))

    def test_case_is_converted_to_a_monitored_trip(self) -> None:
        case = get_case("JB-SYN-0001")
        trip = trip_from_case(case)
        self.assertEqual("JB-SYN-0001", trip["case_id"])
        self.assertEqual(3, len(trip["segments"]))
        self.assertIsNone(trip["disruption"])
        self.assertEqual(case["user_query"], trip["simulation"]["user_query"])

    def test_unknown_product_case_exposes_supported_confirmation_options(self) -> None:
        trip = trip_from_case(get_case("JB-SYN-0541"))
        options = trip["simulation"]["product_options"]
        self.assertGreaterEqual(len(options), 5)
        self.assertIn("SG_PLATINUM_CHARGE", {item["code"] for item in options})

    def test_expected_recovery_result_never_needs_an_api_call(self) -> None:
        case = get_case("JB-SYN-0001")
        result = recovery_case_from_synthetic(case)
        self.assertEqual("synthetic_expected", result["processing_mode"])
        self.assertEqual("flight_delay", result["disruption"]["event_type"])
        self.assertTrue(result["recovery_actions"])
        self.assertTrue(result["benefit_match"]["policy_evidence"])
        self.assertTrue(result["human_review_required"])

    def test_product_need_metrics_are_derived_from_600_rows(self) -> None:
        insights = dataset_insights()
        self.assertEqual(600, insights["dataset_size"])
        self.assertEqual(420, insights["headline_metrics"]["needs_explanation_or_triage"]["count"])
        self.assertEqual(180, insights["headline_metrics"]["missing_key_documents"]["count"])
        self.assertEqual(353, insights["headline_metrics"]["non_english_cases"]["count"])


if __name__ == "__main__":
    unittest.main()
