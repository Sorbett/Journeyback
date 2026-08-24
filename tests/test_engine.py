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


class PolicyQuestionFakeLLMClient(FakeLLMClient):
    def structured(self, **kwargs):  # type: ignore[no-untyped-def]
        result = super().structured(**kwargs)
        if kwargs["schema_name"] == "journeyback_guidance":
            result["missing_information"] = [
                "Official policy certificate current wording",
                "Date and time of claim submission",
                "None - all other required information is available",
                "Whether the delay meets the benefit duration threshold",
                "Property Irregularity Report number",
            ]
        return result


class AlreadyVerifiedAlternativeFakeLLMClient(FakeLLMClient):
    def structured(self, **kwargs):  # type: ignore[no-untyped-def]
        result = super().structured(**kwargs)
        if kwargs["schema_name"] == "journeyback_guidance":
            result["missing_information"] = [
                "Whether the alternative flight offered was within a reasonable timeframe."
            ]
        return result


class FlightDelayWithIrrelevantPIRClient(FakeLLMClient):
    def structured(self, **kwargs):  # type: ignore[no-untyped-def]
        result = super().structured(**kwargs)
        if kwargs["schema_name"] == "journeyback_guidance":
            payload = json.loads(kwargs["input_text"])
            baggage = next(
                item
                for item in payload["retrieved_evidence"]
                if "BAGGAGE" in item["chunk_id"]
            )
            result["missing_information"] = [
                "Property Irregularity Report (not applicable for flight delay)",
            ]
            result["next_steps"] = [
                {
                    "priority": 1,
                    "title": "Request a PIR",
                    "description": "Ask the baggage desk for a Property Irregularity Report.",
                },
                {
                    "priority": 2,
                    "title": "Keep the carrier confirmation",
                    "description": "Retain the written flight-delay record.",
                },
            ]
            result["citations"] = [
                {
                    "chunk_id": baggage["chunk_id"],
                    "relevance": "Incorrect baggage evidence",
                }
            ]
        return result


class JourneybackEngineTests(unittest.TestCase):
    def test_flight_delay_cannot_request_or_cite_baggage_pir_evidence(self) -> None:
        engine = JourneybackEngine(
            settings=LLMSettings(
                model="test-reasoning-model",
                embedding_model="test-embedding-model",
            ),
            client=FlightDelayWithIrrelevantPIRClient(),
            cache_path=False,
        )
        result = engine.evaluate({
            "message": (
                "Verified product: The Platinum Card (SG_PLATINUM_CHARGE)\n"
                "Event: flight_delay lasting 720 minutes\n"
                "Carrier confirmation and itemised meal receipts are verified."
            )
        })

        self.assertEqual("flight_delay", result["incident"]["incident_type"])
        self.assertEqual([], result["missing_information"])
        self.assertNotIn("PIR", " ".join(step["title"] for step in result["next_steps"]))
        self.assertTrue(result["trace"]["rejected_incident_citations"])
        self.assertTrue(result["trace"]["filtered_next_steps"])
        self.assertIn("flight delay", result["trace"]["retrieval_query"])
        self.assertNotIn("baggage", result["trace"]["retrieval_query"])

    def test_verified_alternative_fact_is_not_requested_again(self) -> None:
        engine = JourneybackEngine(
            settings=LLMSettings(
                model="test-reasoning-model",
                embedding_model="test-embedding-model",
            ),
            client=AlreadyVerifiedAlternativeFakeLLMClient(),
            cache_path=False,
        )
        result = engine.evaluate({
            "message": f"{MESSAGE}\nALTERNATIVE_WITHIN_FOUR_HOURS: NO"
        })

        self.assertEqual([], result["missing_information"])
        self.assertEqual(
            ["Whether the alternative flight offered was within a reasonable timeframe."],
            result["trace"]["filtered_missing_information"],
        )

    def test_policy_questions_are_not_returned_as_customer_upload_requests(self) -> None:
        client = PolicyQuestionFakeLLMClient()
        engine = JourneybackEngine(
            settings=LLMSettings(
                model="test-reasoning-model",
                embedding_model="test-embedding-model",
            ),
            client=client,
            cache_path=False,
        )
        result = engine.evaluate({"message": MESSAGE})

        self.assertEqual(["Property Irregularity Report number"], result["missing_information"])
        self.assertEqual(
            [
                "Official policy certificate current wording",
                "Date and time of claim submission",
                "None - all other required information is available",
                "Whether the delay meets the benefit duration threshold",
            ],
            result["trace"]["filtered_missing_information"],
        )

    def test_natural_language_runs_two_llm_stages_and_semantic_rag(self) -> None:
        engine, client = fake_engine()
        result = engine.evaluate({"message": MESSAGE})

        self.assertEqual(["journeyback_incident", "journeyback_guidance"], client.structured_calls)
        self.assertGreaterEqual(client.embedding_calls, 2)
        self.assertEqual("llm_rag", result["mode"])
        self.assertEqual("baggage_delay", result["incident"]["incident_type"])
        self.assertTrue(result["policy_evidence"])
        self.assertTrue(
            all(
                item["product_code"] == "SG_PLATINUM_CHARGE"
                for item in result["policy_evidence"]
            )
        )

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

    def test_retrieval_can_be_scoped_to_the_confirmed_product(self) -> None:
        client = FakeLLMClient()
        retriever = SemanticRetriever(
            client=client,
            embedding_model="test-embedding-model",
            cache_path=False,
        )
        results = retriever.retrieve(
            "missed connection travel inconvenience",
            top_k=8,
            product_code="SG_TRUE_CASHBACK",
        )
        self.assertTrue(results)
        self.assertEqual(
            {"SG_TRUE_CASHBACK"}, {item["product_code"] for item in results}
        )

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
