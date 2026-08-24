from __future__ import annotations

import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.pipeline_evidence import (  # noqa: E402
    PIPELINE_TEST_ROOT,
    pipeline_test_kit,
    pipeline_test_summary,
)
from journeyback.synthetic_demo import synthetic_cases  # noqa: E402


UPLOADABLE_CODES = {
    "flight_ticket",
    "carrier_confirmation",
    "pir",
    "receipts",
    "policy_certificate",
}
POST_CONFIRMATION_CODES = {"flight_ticket", "carrier_confirmation", "receipts"}


class PipelineEvidenceTests(unittest.TestCase):
    def test_every_upload_blocked_case_has_a_matching_package(self) -> None:
        benchmark_cases = {
            case["case_id"]: case
            for case in synthetic_cases()
            if set(case["expected_missing_documents"]) & UPLOADABLE_CODES
        }
        index = json.loads((PIPELINE_TEST_ROOT / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(120, len(benchmark_cases))
        post_confirmation_cases = {
            case["case_id"]: case
            for case in synthetic_cases()
            if "exact_card_product" in case["expected_missing_documents"]
            and case["event_type"] == "flight_delay"
        }
        expected_package_ids = set(benchmark_cases) | set(post_confirmation_cases)
        self.assertEqual(23, len(post_confirmation_cases))
        self.assertEqual(143, index["package_count"])
        self.assertEqual(265, index["file_count"])
        self.assertEqual(expected_package_ids, {item["case_id"] for item in index["packages"]})

        for case_id, case in benchmark_cases.items():
            manifest = json.loads(
                (PIPELINE_TEST_ROOT / case_id / "manifest.json").read_text(encoding="utf-8")
            )
            actual_codes = {item["evidence_code"] for item in manifest["files"]}
            expected_codes = set(case["expected_missing_documents"]) & UPLOADABLE_CODES
            if case_id == "JB-SYN-0331":
                expected_codes = {"flight_ticket", "carrier_confirmation", "receipts"}
            self.assertEqual(expected_codes, actual_codes, case_id)
            self.assertEqual(case["content_hash"], manifest["source_case_hash"])
            self.assertEqual(case["product_code"], manifest["product_code"])

            for item in manifest["files"]:
                content = (PIPELINE_TEST_ROOT / case_id / item["file_name"]).read_bytes()
                self.assertIn(case_id.encode("utf-8"), content)
                self.assertEqual(len(content), item["size_bytes"])
                self.assertEqual(hashlib.sha256(content).hexdigest(), item["sha256"])

        for case_id, case in post_confirmation_cases.items():
            manifest = json.loads(
                (PIPELINE_TEST_ROOT / case_id / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("post_product_confirmation", manifest["package_mode"])
            self.assertTrue(manifest["product_bound_at_runtime"])
            self.assertEqual(
                POST_CONFIRMATION_CODES,
                {item["evidence_code"] for item in manifest["files"]},
            )
            self.assertEqual(case["content_hash"], manifest["source_case_hash"])

    def test_runtime_kit_returns_integrity_checked_api_payload(self) -> None:
        kit = pipeline_test_kit("JB-SYN-0332")

        self.assertEqual("JB-SYN-0332", kit["case_id"])
        self.assertEqual("SG_PLATINUM_CHARGE", kit["product_code"])
        self.assertEqual(
            {"carrier_confirmation", "receipts"},
            {item["evidence_code"] for item in kit["files"]},
        )
        for item in kit["files"]:
            self.assertIn(b"JB-SYN-0332", base64.b64decode(item["content_base64"]))

    def test_all_post_confirmation_kits_bind_the_selected_product(self) -> None:
        cases = [
            case
            for case in synthetic_cases()
            if "exact_card_product" in case["expected_missing_documents"]
            and case["event_type"] == "flight_delay"
        ]
        self.assertEqual(23, len(cases))

        for case in cases:
            with self.subTest(case_id=case["case_id"]):
                kit = pipeline_test_kit(
                    case["case_id"],
                    product_code="SG_PLATINUM_CHARGE",
                )
                self.assertEqual("post_product_confirmation", kit["package_mode"])
                self.assertEqual("SG_PLATINUM_CHARGE", kit["product_code"])
                self.assertEqual(3, len(kit["files"]))
                combined = b"\n".join(
                    base64.b64decode(item["content_base64"])
                    for item in kit["files"]
                )
                self.assertIn(b"THE PLATINUM CARD", combined)
                self.assertIn(b"SG_PLATINUM_CHARGE", combined)
                self.assertIn(b"ITEM_1: MEALS AND REFRESHMENTS", combined)
                self.assertNotIn(b"ITEM_1: UNKNOWN", combined)
                self.assertNotIn(b"{{PRODUCT_", combined)

        with self.assertRaisesRegex(ValueError, "Select a supported"):
            pipeline_test_kit("JB-SYN-0575")

    def test_cases_without_upload_gaps_do_not_expose_a_package(self) -> None:
        self.assertIsNone(pipeline_test_summary("JB-SYN-0001"))
        with self.assertRaisesRegex(ValueError, "No guided pipeline test kit"):
            pipeline_test_kit("JB-SYN-0001")
        with self.assertRaisesRegex(ValueError, "No guided pipeline test kit"):
            pipeline_test_kit("../../.env")


if __name__ == "__main__":
    unittest.main()
