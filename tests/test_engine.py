from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from fakes import FakeLLMClient  # noqa: E402
from journeyback.config import LLMSettings  # noqa: E402
from journeyback.engine import JourneybackEngine  # noqa: E402
from journeyback.llm_client import LLMConfigurationError  # noqa: E402
from journeyback.retrieval import SemanticRetriever  # noqa: E402


MESSAGE = (
    "Operational carrier event: a round-trip itinerary paid with The Platinum Card arrived in Tokyo, "
    "but one checked bag has not been delivered seven hours after arrival. A PIR is not yet available."
)


def fake_engine(*, invalid_citation: bool = False) -> tuple[JourneybackEngine, FakeLLMClient]:
    client = FakeLLMClient(invalid_citation=invalid_citation)
    settings = LLMSettings(model="test-reasoning-model", embedding_model="test-embedding-model")
    engine = JourneybackEngine(settings=settings, client=client, cache_path=False)
    return engine, client


class JourneybackEngineTests(unittest.TestCase):
    def test_natural_language_runs_two_llm_stages_and_semantic_rag(self) -> None:
        engine, client = fake_engine()
        result = engine.evaluate({"message": MESSAGE})

        self.assertEqual(["journeyback_incident", "journeyback_guidance"], client.structured_calls)
        self.assertGreaterEqual(client.embedding_calls, 2)
        self.assertEqual("llm_rag", result["mode"])
        self.assertEqual("baggage_delay", result["incident"]["incident_type"])
        self.assertTrue(result["policy_evidence"])

    def test_hallucinated_citation_is_rejected_and_routes_to_review(self) -> None:
        engine, _ = fake_engine(invalid_citation=True)
        result = engine.evaluate({"message": MESSAGE})

        self.assertEqual("human_review", result["status"])
        self.assertEqual([], result["policy_evidence"])
        self.assertIn("HALLUCINATED-CHUNK", result["trace"]["rejected_citations"])
        self.assertLessEqual(result["confidence"], 0.35)

    def test_safety_contract_is_always_enforced(self) -> None:
        engine, _ = fake_engine()
        result = engine.evaluate({"message": MESSAGE})

        self.assertTrue(result["human_review_required"])
        self.assertIsNone(result["expected_payout_sgd"])
        self.assertIn("does not approve a claim", result["safety_note"])
        json.dumps(result, ensure_ascii=False)

    def test_embedding_retrieval_finds_relevant_baggage_policy(self) -> None:
        client = FakeLLMClient()
        retriever = SemanticRetriever(
            client=client,
            embedding_model="test-embedding-model",
            cache_path=False,
        )
        results = retriever.retrieve("The Platinum Card baggage delay PIR", top_k=8)
        result_ids = {item["chunk_id"] for item in results}
        self.assertIn("POL-SG-PLATINUM-BAGGAGE", result_ids)

    def test_missing_api_key_fails_closed(self) -> None:
        settings = LLMSettings(model="model", embedding_model="embedding")
        engine = JourneybackEngine(settings=settings, cache_path=False)
        with self.assertRaises(LLMConfigurationError):
            engine.evaluate({"message": MESSAGE})

    def test_public_configuration_never_contains_api_key(self) -> None:
        engine, _ = fake_engine()
        summary = engine.runtime_summary()
        self.assertNotIn("api_key", summary)
        self.assertTrue(summary["configured"])

    def test_short_customer_message_is_rejected(self) -> None:
        engine, _ = fake_engine()
        with self.assertRaises(ValueError):
            engine.evaluate({"message": "Delayed"})


if __name__ == "__main__":
    unittest.main()
