from __future__ import annotations

import json
import sys
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


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_engine = JourneybackHandler.engine
        JourneybackHandler.engine = JourneybackEngine(
            settings=LLMSettings(api_key="", model="test-model", embedding_model="test-embedding"),
            client=FakeLLMClient(),
            cache_path=False,
        )
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

    def test_health_endpoint_reports_llm_pipeline_without_key(self) -> None:
        with urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["ready"])
        self.assertEqual(107, payload["knowledge_base"]["chunks"])
        self.assertNotIn("api_key", payload["llm"])

    def test_trip_endpoint_returns_normal_monitored_itinerary(self) -> None:
        with urlopen(f"http://127.0.0.1:{self.port}/api/trip", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual("Tokyo business trip", payload["title"])
        self.assertIsNone(payload["disruption"])
        self.assertEqual("active", payload["monitoring"]["status"])

    def test_detect_endpoint_creates_proactive_recovery_case(self) -> None:
        body = b"{}"
        request = Request(
            f"http://127.0.0.1:{self.port}/api/detect",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual("baggage_delay", payload["disruption"]["event_type"])
        self.assertTrue(payload["benefit_match"]["policy_evidence"])
        self.assertEqual(60, payload["claim_pack"]["completion_percent"])
        self.assertTrue(payload["recovery_actions"])
        self.assertTrue(payload["human_review_required"])


if __name__ == "__main__":
    unittest.main()
