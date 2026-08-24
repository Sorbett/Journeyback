from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.recovery_actions import (  # noqa: E402
    create_recovery_artifact,
    load_reanalysis_snapshot,
    load_recovery_artifact,
    save_reanalysis_snapshot,
)
from journeyback.synthetic_demo import get_case, recovery_case_from_synthetic  # noqa: E402


class RecoveryActionTests(unittest.TestCase):
    def test_live_reanalysis_snapshot_requires_the_same_product_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recovery = {"case_id": "JB-SYN-0331", "processing_mode": "live_llm_rag"}
            save_reanalysis_snapshot(
                case_id="JB-SYN-0331",
                product_code="SG_TRUE_CASHBACK",
                evidence_upload_ids=["UP-test"],
                recovery=recovery,
                artifact_root=root,
            )
            self.assertEqual(
                recovery,
                load_reanalysis_snapshot(
                    case_id="JB-SYN-0331",
                    product_code="SG_TRUE_CASHBACK",
                    evidence_upload_ids=["UP-test"],
                    artifact_root=root,
                ),
            )
            self.assertIsNone(
                load_reanalysis_snapshot(
                    case_id="JB-SYN-0331",
                    product_code="SG_PLATINUM_CHARGE",
                    evidence_upload_ids=["UP-test"],
                    artifact_root=root,
                )
            )

    def test_review_pack_is_persisted_and_downloadable(self) -> None:
        case = get_case("JB-SYN-0001")
        recovery = recovery_case_from_synthetic(case)
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_recovery_artifact(
                case=case,
                action_code="build_evidence_pack",
                recovery=recovery,
                uploaded_evidence=[],
                artifact_root=Path(directory),
            )
            metadata, body = load_recovery_artifact(
                case_id=case["case_id"],
                artifact_id=artifact["artifact_id"],
                artifact_root=Path(directory),
            )
        payload = json.loads(body)
        self.assertEqual("draft_for_formal_review", payload["status"])
        self.assertTrue(payload["guidance"]["human_review_required"])
        self.assertEqual("application/json", metadata["media_type"])
        self.assertTrue(artifact["download_path"].startswith("/api/artifact?"))

    def test_carrier_action_creates_a_real_message_draft(self) -> None:
        case = get_case("JB-SYN-0001")
        recovery = recovery_case_from_synthetic(case)
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_recovery_artifact(
                case=case,
                action_code="prepare_carrier_request",
                recovery=recovery,
                uploaded_evidence=[],
                artifact_root=Path(directory),
            )
        self.assertEqual("message_draft", artifact["preview"]["type"])
        self.assertIn("Please confirm", artifact["preview"]["body"])


if __name__ == "__main__":
    unittest.main()
