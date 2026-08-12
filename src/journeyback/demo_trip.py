"""Proactive travel-monitoring scenario used by the JourneyBack MVP."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


BASE_TRIP: dict[str, Any] = {
    "trip_id": "TRIP-SG-TYO-2026-0812",
    "traveller": {"display_name": "Alex Morgan", "party_size": 1},
    "title": "Tokyo business trip",
    "route": "Singapore to Tokyo",
    "date_range": "12–18 August 2026",
    "card": {
        "product_code": "SG_PLATINUM_CHARGE",
        "product_name": "The Platinum Card",
        "payment_verified": True,
        "display_number": "Card ending 1008",
    },
    "monitoring": {
        "status": "active",
        "label": "Trip monitoring active",
        "last_checked": "12 Aug 2026, 16:20 SGT",
        "sources": ["Itinerary", "Card payment", "Carrier status"],
    },
    "segments": [
        {
            "segment_id": "SQ012-SIN-NRT",
            "type": "flight",
            "carrier": "Singapore Airlines",
            "service_number": "SQ 12",
            "origin_code": "SIN",
            "origin_city": "Singapore",
            "destination_code": "NRT",
            "destination_city": "Tokyo",
            "departure_local": "12 Aug, 09:25",
            "arrival_local": "12 Aug, 17:30",
            "status": "arrived",
            "status_label": "Arrived",
        },
        {
            "segment_id": "TOKYO-STAY",
            "type": "hotel",
            "name": "The Gate Hotel Tokyo",
            "location": "Ginza, Tokyo",
            "check_in": "12 Aug",
            "check_out": "18 Aug",
            "status": "confirmed",
            "status_label": "Confirmed",
        },
        {
            "segment_id": "SQ011-NRT-SIN",
            "type": "flight",
            "carrier": "Singapore Airlines",
            "service_number": "SQ 11",
            "origin_code": "NRT",
            "origin_city": "Tokyo",
            "destination_code": "SIN",
            "destination_city": "Singapore",
            "departure_local": "18 Aug, 19:00",
            "arrival_local": "19 Aug, 01:15",
            "status": "scheduled",
            "status_label": "Scheduled",
        },
    ],
    "disruption": None,
}


DETECTED_DISRUPTION: dict[str, Any] = {
    "event_id": "EVT-BAG-SQ012-20260812",
    "event_type": "baggage_delay",
    "severity": "attention",
    "headline": "Checked baggage has not been delivered",
    "summary": "A carrier baggage-status signal shows that one checked bag from SQ 12 has not been delivered 7 hours after arrival in Tokyo.",
    "detected_at": "13 Aug 2026, 00:30 JST",
    "duration": "7 hours after arrival",
    "location": "Tokyo Narita Airport",
    "carrier_reference": "BAG-SQ12-4817",
    "source": "Simulated carrier status feed",
    "source_confidence": "High",
}


def trip_snapshot(*, disruption_detected: bool = False) -> dict[str, Any]:
    """Return a clean normal-trip or detected-disruption view."""

    trip = deepcopy(BASE_TRIP)
    if disruption_detected:
        trip["disruption"] = deepcopy(DETECTED_DISRUPTION)
        trip["monitoring"] = {
            **trip["monitoring"],
            "status": "attention",
            "label": "Disruption detected",
            "last_checked": "13 Aug 2026, 00:30 JST",
        }
        trip["segments"][0]["status"] = "attention"
        trip["segments"][0]["status_label"] = "Baggage delayed"
    return trip


def disruption_event_message(trip: dict[str, Any]) -> str:
    """Assemble the machine-generated context passed to the LLM/RAG pipeline."""

    disruption = trip.get("disruption")
    if not disruption:
        raise ValueError("No disruption has been detected for this trip.")
    card = trip["card"]
    flight = trip["segments"][0]
    payment = "verified" if card["payment_verified"] else "not verified"
    return (
        f"Operational event for a Singapore-issued {card['product_name']} ({card['product_code']}). "
        f"The round-trip itinerary payment is {payment} on this Card. "
        f"{flight['service_number']} from {flight['origin_code']} to {flight['destination_code']} arrived at "
        f"{flight['arrival_local']}. One checked bag has not been delivered {disruption['duration']}. "
        f"Location: {disruption['location']}. Carrier event reference: {disruption['carrier_reference']}. "
        "The itinerary and Card payment record are available. A Property Irregularity Report and itemised "
        "receipts are not yet available. Determine the most relevant public benefit wording and the safest "
        "time-sensitive recovery steps."
    )


def build_recovery_case(trip: dict[str, Any], guidance: dict[str, Any]) -> dict[str, Any]:
    """Combine verified system data and grounded LLM guidance for the UI."""

    disruption = trip["disruption"]
    claim_items = [
        {"code": "itinerary", "label": "Round-trip itinerary", "status": "complete", "source": "Amex travel record"},
        {"code": "card_payment", "label": "Card payment verification", "status": "complete", "source": trip["card"]["display_number"]},
        {"code": "carrier_event", "label": "Carrier event record", "status": "complete", "source": disruption["carrier_reference"]},
        {"code": "pir", "label": "Property Irregularity Report (PIR)", "status": "required", "source": "Request from airline"},
        {"code": "receipts", "label": "Itemised essential-purchase receipts", "status": "required", "source": "Upload after purchase"},
    ]
    completed = sum(item["status"] == "complete" for item in claim_items)
    return {
        "case_id": "JB-2026-0812-0041",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "trip": trip,
        "disruption": disruption,
        "benefit_match": {
            "status": guidance["status"],
            "status_title": guidance["status_title"],
            "headline": guidance["headline"],
            "summary": guidance["summary"],
            "confidence": guidance["confidence"],
            "product_name": trip["card"]["product_name"],
            "payment_verified": trip["card"]["payment_verified"],
            "policy_evidence": guidance["policy_evidence"],
        },
        "recovery_actions": guidance["next_steps"],
        "missing_information": guidance["missing_information"],
        "claim_pack": {
            "completed": completed,
            "total": len(claim_items),
            "completion_percent": round(100 * completed / len(claim_items)),
            "items": claim_items,
        },
        "human_review_required": guidance["human_review_required"],
        "safety_note": guidance["safety_note"],
        "trace": guidance["trace"],
    }
