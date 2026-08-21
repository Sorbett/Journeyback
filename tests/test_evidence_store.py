from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.evidence_store import (  # noqa: E402
    enrich_case,
    load_evidence,
    reanalysis_message,
    save_evidence,
)
from journeyback.synthetic_demo import get_case  # noqa: E402


class EvidenceStoreTests(unittest.TestCase):
    def test_readable_upload_content_and_note_reach_reanalysis_context(self) -> None:
        content = b"Carrier confirms the connection was missed at 17:40 UTC."
        with tempfile.TemporaryDirectory() as directory:
            upload_root = Path(directory)
            saved = save_evidence(
                case_id="JB-SYN-0331",
                evidence_code="flight_ticket",
                file_name="confirmation.txt",
                mime_type="text/plain",
                content_base64=base64.b64encode(content).decode("ascii"),
                evidence_note="Booking reference JB-DEMO-33",
                upload_root=upload_root,
            )
            evidence = load_evidence(
                case_id="JB-SYN-0331",
                upload_ids=[saved["upload_id"]],
                upload_root=upload_root,
            )

        enriched = enrich_case(
            get_case("JB-SYN-0331"), product_code=None, uploaded_evidence=evidence
        )
        message = reanalysis_message(enriched, uploaded_evidence=evidence)
        self.assertIn("Carrier confirms the connection was missed", message)
        self.assertIn("Booking reference JB-DEMO-33", message)
        self.assertNotIn("flight_ticket", enriched["expected_missing_documents"])


if __name__ == "__main__":
    unittest.main()
