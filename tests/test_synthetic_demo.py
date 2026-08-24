from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.synthetic_demo import (  # noqa: E402
    dataset_insights,
    get_case,
    recovery_case_after_product_confirmation,
    recovery_case_from_synthetic,
    synthetic_cases,
    trip_from_case,
)
from journeyback.evidence_store import enrich_case  # noqa: E402


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
        case = get_case("JB-SYN-0541")
        trip = trip_from_case(case)
        options = trip["simulation"]["product_options"]
        self.assertGreaterEqual(len(options), 5)
        self.assertIn("SG_PLATINUM_CHARGE", {item["code"] for item in options})
        recovery = recovery_case_from_synthetic(case)
        question = recovery["workspace"]["primary_question"]
        self.assertEqual("product", question["type"])
        self.assertEqual("exact_card_product", question["evidence_code"])

    def test_all_product_blocked_flight_cases_expose_post_confirmation_pipelines(self) -> None:
        cases = [
            case
            for case in synthetic_cases()
            if "exact_card_product" in case["expected_missing_documents"]
            and case["event_type"] == "flight_delay"
        ]
        self.assertEqual(23, len(cases))

        for case in cases:
            case_id = case["case_id"]
            recovery = recovery_case_from_synthetic(get_case(case_id))
            question = recovery["workspace"]["primary_question"]
            pipeline = question["post_confirmation_pipeline"]
            self.assertEqual("product", question["type"])
            self.assertEqual(3, pipeline["file_count"])
            self.assertEqual("product_confirmation", pipeline["trigger"])

    def test_confirmed_product_advances_to_specialist_review(self) -> None:
        case = dict(get_case("JB-SYN-0543"))
        case["product_code"] = "SG_PLATINUM_CHARGE"
        case["product_name"] = "The Platinum Card"
        case["product_resolution_status"] = "resolved"
        case["expected_missing_documents"] = []

        recovery = recovery_case_after_product_confirmation(case)

        self.assertEqual("validated_input", recovery["processing_mode"])
        self.assertNotIn(
            "exact_card_product",
            {item["code"] for item in recovery["claim_pack"]["items"]},
        )
        self.assertEqual("review", recovery["workspace"]["primary_question"]["type"])

    def test_all_product_blocked_cases_advance_after_card_confirmation(self) -> None:
        product_blocked_cases = [
            case
            for case in synthetic_cases()
            if "exact_card_product" in case["expected_missing_documents"]
        ]

        self.assertEqual(60, len(product_blocked_cases))
        self.assertEqual(
            {"card_loss", "flight_delay", "hotel_issue"},
            {case["event_type"] for case in product_blocked_cases},
        )
        for case in product_blocked_cases:
            enriched = enrich_case(
                case,
                product_code="SG_PLATINUM_CHARGE",
                uploaded_evidence=[],
            )
            recovery = recovery_case_after_product_confirmation(enriched)
            claim_codes = {item["code"] for item in recovery["claim_pack"]["items"]}
            primary_question = recovery["workspace"]["primary_question"]
            action_codes = {
                item["code"] for item in recovery["workspace"]["handoff"]["actions"]
            }

            self.assertNotIn("exact_card_product", claim_codes, case["case_id"])
            self.assertTrue(
                primary_question is None or primary_question["type"] != "product",
                case["case_id"],
            )
            self.assertIn("build_evidence_pack", action_codes, case["case_id"])
            self.assertEqual(
                "The Platinum Card",
                recovery["trip"]["card"]["product_name"],
                case["case_id"],
            )

    def test_golden_case_exposes_a_one_click_guided_pipeline(self) -> None:
        recovery = recovery_case_from_synthetic(get_case("JB-SYN-0331"))
        question = recovery["workspace"]["primary_question"]

        self.assertEqual("upload", question["type"])
        self.assertEqual("flight_ticket", question["evidence_code"])
        self.assertEqual(3, question["guided_pipeline"]["file_count"])

    def test_each_upload_case_exposes_its_matched_evidence_package(self) -> None:
        recovery = recovery_case_from_synthetic(get_case("JB-SYN-0332"))
        question = recovery["workspace"]["primary_question"]

        self.assertEqual("upload", question["type"])
        self.assertEqual(2, question["guided_pipeline"]["file_count"])
        self.assertEqual(
            {"carrier_confirmation", "receipts"},
            {item["evidence_code"] for item in question["guided_pipeline"]["files"]},
        )

    def test_expected_recovery_result_never_needs_an_api_call(self) -> None:
        case = get_case("JB-SYN-0001")
        result = recovery_case_from_synthetic(case)
        self.assertEqual("synthetic_expected", result["processing_mode"])
        self.assertEqual("flight_delay", result["disruption"]["event_type"])
        self.assertTrue(result["recovery_actions"])
        self.assertTrue(result["benefit_match"]["policy_evidence"])
        self.assertTrue(result["human_review_required"])
        self.assertEqual(6, len(result["workspace"]["activity"]))
        self.assertIn(result["workspace"]["phase"], {"needs_input", "handoff_ready"})

    def test_product_need_metrics_are_derived_from_600_rows(self) -> None:
        insights = dataset_insights()
        self.assertEqual(600, insights["dataset_size"])
        self.assertEqual(420, insights["headline_metrics"]["needs_explanation_or_triage"]["count"])
        self.assertEqual(180, insights["headline_metrics"]["missing_key_documents"]["count"])
        self.assertEqual(353, insights["headline_metrics"]["non_english_cases"]["count"])


if __name__ == "__main__":
    unittest.main()
