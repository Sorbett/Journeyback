from __future__ import annotations

import base64
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from fakes import FakeLLMClient  # noqa: E402
from journeyback.config import LLMSettings  # noqa: E402
from journeyback.engine import JourneybackEngine  # noqa: E402
from journeyback.server import JourneybackHandler  # noqa: E402
from journeyback.synthetic_demo import synthetic_cases  # noqa: E402


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_engine = JourneybackHandler.engine
        cls.previous_upload_root = JourneybackHandler.upload_root
        cls.upload_directory = tempfile.TemporaryDirectory()
        JourneybackHandler.engine = JourneybackEngine(
            settings=LLMSettings(model="test-model", embedding_model="test-embedding"),
            client=FakeLLMClient(),
            cache_path=False,
        )
        JourneybackHandler.upload_root = Path(cls.upload_directory.name)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), JourneybackHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        JourneybackHandler.engine = cls.previous_engine
        JourneybackHandler.upload_root = cls.previous_upload_root
        cls.upload_directory.cleanup()

    def test_health_endpoint_reports_llm_pipeline_without_key(self) -> None:
        with urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["ready"])
        self.assertEqual(107, payload["knowledge_base"]["chunks"])
        self.assertNotIn("api_key", payload["llm"])
        self.assertIn("embedding_cache", payload["llm"])

    def test_trip_endpoint_returns_requested_synthetic_traveller(self) -> None:
        with urlopen(
            f"http://127.0.0.1:{self.port}/api/trip?case_id=JB-SYN-0001", timeout=2
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual("JB-SYN-0001", payload["case_id"])
        self.assertTrue(payload["synthetic"])
        self.assertIsNone(payload["disruption"])
        self.assertEqual("active", payload["monitoring"]["status"])
        self.assertEqual(600, payload["simulation"]["dataset_size"])

    def test_detect_endpoint_materialises_fast_expected_result(self) -> None:
        body = json.dumps({"case_id": "JB-SYN-0001", "live": False}).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}/api/detect",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual("flight_delay", payload["disruption"]["event_type"])
        self.assertEqual("synthetic_expected", payload["processing_mode"])
        self.assertTrue(payload["benefit_match"]["policy_evidence"])
        self.assertTrue(payload["recovery_actions"])
        self.assertTrue(payload["human_review_required"])
        self.assertLess(payload["response_time_ms"], 1_000)

    def test_insights_endpoint_aggregates_all_generated_cases(self) -> None:
        with urlopen(f"http://127.0.0.1:{self.port}/api/demo/insights", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(600, payload["dataset_size"])
        self.assertEqual(70.0, payload["headline_metrics"]["needs_explanation_or_triage"]["percent"])

    def test_evaluation_routes_lead_with_product_outcomes(self) -> None:
        with urlopen(f"http://127.0.0.1:{self.port}/evaluation", timeout=2) as response:
            product_report = response.read().decode("utf-8")
        with urlopen(
            f"http://127.0.0.1:{self.port}/evaluation/retrieval", timeout=2
        ) as response:
            retrieval_report = response.read().decode("utf-8")

        self.assertIn("PRODUCT OUTCOME BENCHMARK", product_report)
        self.assertIn("Product outcomes come first", product_report)
        self.assertIn("COMPONENT EVALUATION", retrieval_report)

    def test_guided_pipeline_endpoint_returns_the_three_curated_files(self) -> None:
        with urlopen(
            f"http://127.0.0.1:{self.port}/api/demo/pipeline-test-kit?case_id=JB-SYN-0331",
            timeout=2,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("JB-SYN-0331", payload["case_id"])
        self.assertEqual("SG_TRUE_CASHBACK", payload["product_code"])
        self.assertEqual(
            {"flight_ticket", "carrier_confirmation", "receipts"},
            {item["evidence_code"] for item in payload["files"]},
        )
        self.assertEqual(3, len(payload["files"]))
        for item in payload["files"]:
            document = base64.b64decode(item["content_base64"])
            self.assertIn(b"JB-SYN-0331", document)
            self.assertEqual("text/plain", item["mime_type"])

    def test_guided_pipeline_endpoint_returns_the_current_cases_matched_files(self) -> None:
        with urlopen(
            f"http://127.0.0.1:{self.port}/api/demo/pipeline-test-kit?case_id=JB-SYN-0332",
            timeout=2,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("JB-SYN-0332", payload["case_id"])
        self.assertEqual("SG_PLATINUM_CHARGE", payload["product_code"])
        self.assertEqual(
            {"carrier_confirmation", "receipts"},
            {item["evidence_code"] for item in payload["files"]},
        )
        self.assertEqual(2, len(payload["files"]))

    def test_post_confirmation_pipeline_endpoint_binds_the_selected_card(self) -> None:
        with urlopen(
            f"http://127.0.0.1:{self.port}/api/demo/pipeline-test-kit"
            "?case_id=JB-SYN-0575&product_code=SG_PLATINUM_CHARGE",
            timeout=2,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("post_product_confirmation", payload["package_mode"])
        self.assertEqual("SG_PLATINUM_CHARGE", payload["product_code"])
        self.assertEqual(3, len(payload["files"]))
        combined = b"\n".join(
            base64.b64decode(item["content_base64"]) for item in payload["files"]
        )
        self.assertIn(b"THE PLATINUM CARD", combined)
        self.assertNotIn(b"{{PRODUCT_", combined)

    def test_post_confirmation_evidence_advances_the_live_case(self) -> None:
        with urlopen(
            f"http://127.0.0.1:{self.port}/api/demo/pipeline-test-kit"
            "?case_id=JB-SYN-0575&product_code=SG_PLATINUM_CHARGE",
            timeout=2,
        ) as response:
            kit = json.loads(response.read().decode("utf-8"))

        upload_ids = []
        for item in kit["files"]:
            upload_body = json.dumps({
                "case_id": "JB-SYN-0575",
                "evidence_code": item["evidence_code"],
                "file_name": item["file_name"],
                "mime_type": item["mime_type"],
                "content_base64": item["content_base64"],
                "evidence_note": item["evidence_note"],
            }).encode("utf-8")
            upload_request = Request(
                f"http://127.0.0.1:{self.port}/api/evidence",
                data=upload_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(upload_request, timeout=2) as response:
                upload = json.loads(response.read().decode("utf-8"))
            upload_ids.append(upload["upload_id"])

        reanalyse_body = json.dumps({
            "case_id": "JB-SYN-0575",
            "product_code": "SG_PLATINUM_CHARGE",
            "evidence_upload_ids": upload_ids,
        }).encode("utf-8")
        reanalyse_request = Request(
            f"http://127.0.0.1:{self.port}/api/reanalyse",
            data=reanalyse_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(reanalyse_request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        item_status = {
            item["code"]: item["status"] for item in payload["claim_pack"]["items"]
        }
        self.assertEqual("live_llm_rag", payload["processing_mode"])
        self.assertEqual("The Platinum Card", payload["trip"]["card"]["product_name"])
        self.assertNotIn("exact_card_product", item_status)
        self.assertEqual("complete", item_status["flight_ticket"])
        self.assertEqual("complete", item_status["carrier_confirmation"])
        self.assertEqual("complete", item_status["receipts"])

    def test_evidence_file_is_persisted_before_it_can_be_reanalysed(self) -> None:
        document = b"%PDF-1.4 synthetic demo evidence"
        body = json.dumps({
            "case_id": "JB-SYN-0331",
            "evidence_code": "carrier_confirmation",
            "file_name": "carrier-confirmation.pdf",
            "mime_type": "application/pdf",
            "content_base64": base64.b64encode(document).decode("ascii"),
            "evidence_note": "Carrier issued written confirmation.",
        }).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}/api/evidence",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("carrier_confirmation", payload["evidence_code"])
        self.assertEqual(len(document), payload["size_bytes"])
        stored = list(Path(self.upload_directory.name).rglob("*.pdf"))
        self.assertEqual(1, len(stored))
        self.assertEqual(document, stored[0].read_bytes())

    def test_product_confirmation_runs_live_llm_rag_reanalysis(self) -> None:
        body = json.dumps({
            "case_id": "JB-SYN-0541",
            "product_code": "SG_PLATINUM_CHARGE",
            "evidence_upload_ids": [],
        }).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}/api/reanalyse",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("live_llm_rag", payload["processing_mode"])
        self.assertEqual("The Platinum Card", payload["trip"]["card"]["product_name"])
        self.assertIsNone(payload["benefit_match"]["expected_eligibility"])
        self.assertNotIn(
            "exact_card_product",
            {item["code"] for item in payload["claim_pack"]["items"]},
        )
        self.assertEqual(100, payload["claim_pack"]["completion_percent"])
        self.assertFalse(
            any(item["code"].startswith("llm_required_") for item in payload["claim_pack"]["items"])
        )
        self.assertEqual("SG_PLATINUM_CHARGE", payload["submitted_information"]["product_code"])

    def test_uncovered_case_accepts_a_supported_card_confirmation(self) -> None:
        body = json.dumps({
            "case_id": "JB-SYN-0543",
            "product_code": "SG_PLATINUM_CHARGE",
            "evidence_upload_ids": [],
        }).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}/api/reanalyse",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("live_llm_rag", payload["processing_mode"])
        self.assertEqual("The Platinum Card", payload["trip"]["card"]["product_name"])
        self.assertEqual("SG_PLATINUM_CHARGE", payload["submitted_information"]["product_code"])
        primary_question = payload["workspace"]["primary_question"]
        self.assertTrue(primary_question is None or primary_question["type"] != "product")

    def test_product_confirmation_advances_the_wallet_before_live_analysis(self) -> None:
        body = json.dumps({
            "case_id": "JB-SYN-0543",
            "product_code": "SG_PLATINUM_CHARGE",
        }).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}/api/product-confirmation",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual("validated_input", payload["processing_mode"])
        self.assertEqual("The Platinum Card", payload["trip"]["card"]["product_name"])
        self.assertNotIn(
            "exact_card_product",
            {item["code"] for item in payload["claim_pack"]["items"]},
        )
        self.assertEqual("review", payload["workspace"]["primary_question"]["type"])
        self.assertEqual("SG_PLATINUM_CHARGE", payload["submitted_information"]["product_code"])

    def test_all_product_blocked_cases_advance_through_live_reanalysis(self) -> None:
        product_blocked_cases = [
            case
            for case in synthetic_cases()
            if "exact_card_product" in case["expected_missing_documents"]
        ]

        self.assertEqual(60, len(product_blocked_cases))
        for case in product_blocked_cases:
            body = json.dumps({
                "case_id": case["case_id"],
                "product_code": "SG_PLATINUM_CHARGE",
                "evidence_upload_ids": [],
            }).encode("utf-8")
            request = Request(
                f"http://127.0.0.1:{self.port}/api/reanalyse",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))

            claim_codes = {item["code"] for item in payload["claim_pack"]["items"]}
            primary_question = payload["workspace"]["primary_question"]
            self.assertEqual("live_llm_rag", payload["processing_mode"], case["case_id"])
            self.assertNotIn("exact_card_product", claim_codes, case["case_id"])
            self.assertTrue(
                primary_question is None or primary_question["type"] != "product",
                case["case_id"],
            )
            self.assertEqual(
                "SG_PLATINUM_CHARGE",
                payload["submitted_information"]["product_code"],
                case["case_id"],
            )

    def test_curated_golden_path_runs_from_upload_to_review_pack(self) -> None:
        fixture_root = PROJECT_ROOT / "data" / "pipeline_test" / "JB-SYN-0331"
        fixtures = (
            (fixture_root / "flight_ticket_and_itinerary.txt", "flight_ticket"),
            (fixture_root / "carrier_confirmation.txt", "carrier_confirmation"),
            (fixture_root / "itemised_expense_receipts.txt", "receipts"),
        )
        detected_body = json.dumps({
            "case_id": "JB-SYN-0331",
            "live": False,
        }).encode("utf-8")
        detected_request = Request(
            f"http://127.0.0.1:{self.port}/api/detect",
            data=detected_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(detected_request, timeout=2) as response:
            detected = json.loads(response.read().decode("utf-8"))
        self.assertEqual("flight_ticket", detected["workspace"]["primary_question"]["evidence_code"])

        uploads = []
        for fixture_path, evidence_code in fixtures:
            document = fixture_path.read_bytes()
            upload_body = json.dumps({
                "case_id": "JB-SYN-0331",
                "evidence_code": evidence_code,
                "file_name": fixture_path.name,
                "mime_type": "text/plain",
                "content_base64": base64.b64encode(document).decode("ascii"),
                "evidence_note": f"Verify the synthetic {evidence_code} evidence.",
            }).encode("utf-8")
            upload_request = Request(
                f"http://127.0.0.1:{self.port}/api/evidence",
                data=upload_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(upload_request, timeout=2) as response:
                upload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(upload["inspection"]["text_extracted"])
            self.assertIn("JB-SYN-0331", upload["inspection"]["excerpt"])
            uploads.append(upload)

        reanalyse_body = json.dumps({
            "case_id": "JB-SYN-0331",
            "product_code": "SG_TRUE_CASHBACK",
            "evidence_upload_ids": [upload["upload_id"] for upload in uploads],
        }).encode("utf-8")
        reanalyse_request = Request(
            f"http://127.0.0.1:{self.port}/api/reanalyse",
            data=reanalyse_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(reanalyse_request, timeout=2) as response:
            recovery = json.loads(response.read().decode("utf-8"))
        self.assertEqual("live_llm_rag", recovery["processing_mode"])
        self.assertEqual(
            ["llm_fact_extraction", "bm25_embedding_rrf", "llm_grounded_guidance", "citation_validation"],
            recovery["trace"]["pipeline"],
        )
        self.assertTrue(recovery["benefit_match"]["policy_evidence"])
        item_status = {
            item["code"]: item["status"] for item in recovery["claim_pack"]["items"]
        }
        self.assertEqual("complete", item_status["flight_ticket"])

        action_body = json.dumps({
            "case_id": "JB-SYN-0331",
            "product_code": "SG_TRUE_CASHBACK",
            "evidence_upload_ids": [upload["upload_id"] for upload in uploads],
            "action_code": "build_evidence_pack",
        }).encode("utf-8")
        action_request = Request(
            f"http://127.0.0.1:{self.port}/api/action",
            data=action_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(action_request, timeout=2) as response:
            artifact = json.loads(response.read().decode("utf-8"))
        with urlopen(
            f"http://127.0.0.1:{self.port}{artifact['download_path']}", timeout=2
        ) as response:
            review_pack = json.loads(response.read().decode("utf-8"))
        self.assertEqual("JB-SYN-0331", review_pack["case_id"])
        self.assertEqual(
            {upload["sha256"] for upload in uploads},
            {item["sha256"] for item in review_pack["submitted_evidence"]},
        )
        self.assertEqual(
            recovery["benefit_match"]["headline"], review_pack["guidance"]["headline"]
        )
        self.assertEqual(
            recovery["missing_information"], review_pack["remaining_information"]
        )

    def test_recovery_action_creates_a_downloadable_server_artifact(self) -> None:
        body = json.dumps({
            "case_id": "JB-SYN-0001",
            "action_code": "build_evidence_pack",
            "evidence_upload_ids": [],
        }).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}/api/action",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            artifact = json.loads(response.read().decode("utf-8"))

        self.assertEqual("created", artifact["status"])
        self.assertEqual("review_pack", artifact["preview"]["type"])
        with urlopen(
            f"http://127.0.0.1:{self.port}{artifact['download_path']}", timeout=2
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
            disposition = response.headers["Content-Disposition"]
        self.assertEqual("draft_for_formal_review", payload["status"])
        self.assertIn("attachment", disposition)


if __name__ == "__main__":
    unittest.main()
