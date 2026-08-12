"""Deterministic model double for testing the LLM pipeline without API spend."""

from __future__ import annotations

import json
from typing import Any


KEYWORDS = (
    "platinum",
    "baggage",
    "行李",
    "delay",
    "延误",
    "pir",
    "flight",
    "航班",
    "cancel",
    "取消",
    "connection",
    "转机",
    "krisflyer",
    "reserve",
    "cashback",
    "insurance",
)


class FakeLLMClient:
    def __init__(self, *, invalid_citation: bool = False) -> None:
        self.invalid_citation = invalid_citation
        self.structured_calls: list[str] = []
        self.embedding_calls = 0

    def structured(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        del instructions, schema
        self.structured_calls.append(schema_name)
        if schema_name == "journeyback_incident":
            return {
                "language": "en",
                "summary": "A Platinum Card Member has a seven-hour checked-baggage delay in Tokyo and no PIR yet.",
                "retrieval_query": "The Platinum Card baggage delay 7 hours PIR receipts essential items",
                "product_hint": "The Platinum Card",
                "incident_type": "baggage_delay",
                "location": "Tokyo Narita Airport",
                "timing": "7 hours after arrival",
                "facts": ["Round-trip itinerary paid with The Platinum Card", "Itinerary and Card payment are verified"],
                "documents_mentioned": ["Round-trip itinerary", "Card payment record"],
                "missing_information": ["Property Irregularity Report number"],
            }

        payload = json.loads(input_text)
        evidence = payload["retrieved_evidence"]
        formal = next(
            (item for item in evidence if "BAGGAGE" in item["chunk_id"]),
            next((item for item in evidence if item["document_type"] == "formal_policy_wording"), evidence[0]),
        )
        chunk_id = "HALLUCINATED-CHUNK" if self.invalid_citation else formal["chunk_id"]
        return {
            "status": "need_more_info",
            "headline": "Baggage delay cover may be relevant",
            "summary": "The public wording may apply to this seven-hour baggage delay. A Property Irregularity Report is the most important outstanding evidence.",
            "confidence": 0.82,
            "detected_facts": [
                {"label": "Card", "value": "The Platinum Card"},
                {"label": "Event", "value": "Baggage delayed for 7 hours"},
                {"label": "Location", "value": "Tokyo Narita Airport"},
            ],
            "missing_information": ["Property Irregularity Report number"],
            "next_steps": [
                {"priority": 1, "title": "Request a Property Irregularity Report", "description": "Contact the airline baggage desk and retain the PIR number and written status update."},
                {"priority": 2, "title": "Keep itemised receipts", "description": "Purchase only reasonable essential items and retain itemised receipts and Card payment evidence."},
                {"priority": 3, "title": "Request a formal benefit review", "description": "Submit the verified itinerary, payment record, carrier event and receipts for confirmation."},
            ],
            "decision_basis": ["Carrier status shows a seven-hour baggage delay", "The PIR is not yet available"],
            "citations": [{"chunk_id": chunk_id, "relevance": "Baggage delay benefit wording and evidence requirements"}],
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedding_calls += 1
        return [[float(text.lower().count(keyword)) for keyword in KEYWORDS] for text in texts]
