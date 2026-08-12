from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.demo_trip import disruption_event_message, trip_snapshot  # noqa: E402


class DemoTripTests(unittest.TestCase):
    def test_normal_trip_has_no_disruption(self) -> None:
        trip = trip_snapshot()
        self.assertIsNone(trip["disruption"])
        self.assertEqual("active", trip["monitoring"]["status"])
        self.assertTrue(trip["card"]["payment_verified"])

    def test_detected_trip_changes_status_and_builds_machine_context(self) -> None:
        trip = trip_snapshot(disruption_detected=True)
        message = disruption_event_message(trip)
        self.assertEqual("baggage_delay", trip["disruption"]["event_type"])
        self.assertEqual("attention", trip["monitoring"]["status"])
        self.assertIn("Card payment record", message)
        self.assertIn("not yet available", message)


if __name__ == "__main__":
    unittest.main()
