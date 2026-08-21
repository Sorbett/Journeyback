"""Fast, deterministic demo views backed by the 600-case synthetic benchmark."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from .config import PROJECT_ROOT
from .evidence_store import public_product_options
from .knowledge_base import KnowledgeBase


CASES_PATH = PROJECT_ROOT / "data" / "synthetic" / "journeyback_cases.jsonl"

AIRPORTS = {
    "SIN": ("Singapore", "Singapore Changi"),
    "BKK": ("Bangkok", "Suvarnabhumi"),
    "DPS": ("Bali", "Denpasar"),
    "HKG": ("Hong Kong", "Hong Kong International"),
    "ICN": ("Seoul", "Incheon"),
    "LHR": ("London", "Heathrow"),
    "NRT": ("Tokyo", "Narita"),
    "SYD": ("Sydney", "Kingsford Smith"),
}

CARRIERS = {
    "CARRIER-A": ("Singapore Airlines", "SQ"),
    "CARRIER-B": ("Cathay Pacific", "CX"),
    "CARRIER-C": ("Qantas", "QF"),
    "CARRIER-D": ("Thai Airways", "TG"),
    "CARRIER-E": ("Korean Air", "KE"),
}

EVENT_LABELS = {
    "flight_delay": "Flight delayed",
    "missed_connection": "Connection missed",
    "flight_cancellation": "Flight cancelled",
    "baggage_delay": "Baggage delayed",
    "baggage_loss": "Baggage still missing",
    "card_loss": "Card reported lost",
    "hotel_issue": "Hotel booking issue",
}

EVENT_HEADLINES = {
    "flight_delay": "Flight delayed",
    "missed_connection": "Connection missed",
    "flight_cancellation": "Flight cancelled",
    "baggage_delay": "Baggage delayed",
    "baggage_loss": "Baggage still missing",
    "card_loss": "Card reported lost",
    "hotel_issue": "Hotel booking issue",
}

ELIGIBILITY_PRESENTATION = {
    "potentially_eligible": (
        "act_now",
        "Potential benefit match",
        "Relevant benefit wording was found. Final eligibility requires review.",
        0.86,
    ),
    "unlikely_eligible": (
        "human_review",
        "A policy condition may not be met",
        "A policy condition may not be met. Specialist review is recommended.",
        0.82,
    ),
    "insufficient_information": (
        "need_more_info",
        "More evidence is needed",
        "Additional evidence is needed before review.",
        0.76,
    ),
    "manual_review_required": (
        "human_review",
        "A specialist review is required",
        "This case is near a policy boundary and needs specialist review.",
        0.68,
    ),
    "out_of_scope": (
        "human_review",
        "The exact Card product must be confirmed",
        "Confirm the Card product before showing benefit guidance.",
        0.62,
    ),
}

STATUS_TITLES = {
    "act_now": "Action available",
    "need_more_info": "Information required",
    "human_review": "Manual review required",
}

DOCUMENTS = (
    ("flight_ticket", "Flight ticket and itinerary", "has_flight_ticket", "Booking record"),
    ("carrier_confirmation", "Carrier disruption confirmation", "has_carrier_confirmation", "Carrier record"),
    ("pir", "Property Irregularity Report (PIR)", "has_pir", "Airline baggage desk"),
    ("receipts", "Itemised expense receipts", "has_receipts", "Card transaction record"),
    ("policy_certificate", "Policy certificate", "has_policy_certificate", "Benefit documents"),
)


@lru_cache(maxsize=1)
def synthetic_cases() -> tuple[dict[str, Any], ...]:
    """Load and validate the deterministic benchmark once per server process."""

    cases: list[dict[str, Any]] = []
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            if case.get("synthetic") is not True or not case.get("case_id"):
                raise ValueError("Synthetic demo data contains an invalid record.")
            cases.append(case)
    if not cases:
        raise ValueError("Synthetic demo data is empty.")
    return tuple(cases)


@lru_cache(maxsize=1)
def _case_index() -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in synthetic_cases()}


def get_case(case_id: str | None = None, *, rng: random.Random | None = None) -> dict[str, Any]:
    """Return a requested case or a random traveller when no id is supplied."""

    if case_id:
        try:
            return _case_index()[case_id]
        except KeyError as exc:
            raise ValueError(f"Unknown synthetic case: {case_id}") from exc
    chooser = rng or random.SystemRandom()
    return chooser.choice(synthetic_cases())


def trip_from_case(case: dict[str, Any], *, disruption_detected: bool = False) -> dict[str, Any]:
    """Turn a benchmark record into the premium travel-monitoring UI contract."""

    departure = _parse_datetime(case["scheduled_departure_utc"])
    return_date = departure + timedelta(days=int(case["trip_duration_days"]))
    origin = str(case["origin_airport"])
    destination = str(case["destination_airport"])
    origin_city, _ = AIRPORTS.get(origin, (origin, origin))
    destination_city, destination_airport = AIRPORTS.get(destination, (destination, destination))
    carrier_name, carrier_prefix = CARRIERS.get(case["carrier_code"], ("Partner airline", "JB"))
    service_number = f"{carrier_prefix} {100 + int(case['case_id'][-4:]) % 800}"
    return_number = f"{carrier_prefix} {101 + int(case['case_id'][-4:]) % 800}"
    payment_verified = bool(case["origin_return_paid_with_card"])
    event_label = EVENT_LABELS.get(case["event_type"], "Travel disruption")

    trip: dict[str, Any] = {
        "trip_id": f"TRIP-{case['case_id']}",
        "case_id": case["case_id"],
        "synthetic": True,
        "traveller": {
            "display_name": f"Demo Traveller · {case['case_id'][-4:]}",
            "party_size": int(case["family_size"]),
            "traveller_type": str(case["traveler_type"]).replace("_", " ").title(),
            "age_band": _age_band(int(case["traveler_age"])),
        },
        "title": f"{destination_city} journey",
        "route": f"{origin_city} to {destination_city}",
        "date_range": _date_range(departure, return_date),
        "card": {
            "product_code": case["product_code"],
            "product_name": case["product_name"],
            "payment_verified": payment_verified,
            "display_number": "Synthetic payment record",
        },
        "monitoring": {
            "status": "active",
            "label": "Journey monitoring active",
            "last_checked": "Live demo signal",
            "sources": ["Itinerary", "Card payment", "Carrier status"],
        },
        "segments": [
            {
                "segment_id": f"{service_number.replace(' ', '')}-{origin}-{destination}",
                "type": "flight",
                "carrier": carrier_name,
                "service_number": service_number,
                "origin_code": origin,
                "origin_city": origin_city,
                "destination_code": destination,
                "destination_city": destination_city,
                "departure_local": _short_datetime(departure),
                "arrival_local": _short_datetime(departure + timedelta(hours=7)),
                "status": "scheduled",
                "status_label": "Monitored",
            },
            {
                "segment_id": f"STAY-{destination}-{case['case_id']}",
                "type": "hotel",
                "name": f"Demo stay · {destination_city}",
                "location": destination_airport,
                "check_in": _short_date(departure),
                "check_out": _short_date(return_date),
                "status": "confirmed",
                "status_label": "Confirmed",
            },
            {
                "segment_id": f"{return_number.replace(' ', '')}-{destination}-{origin}",
                "type": "flight",
                "carrier": carrier_name,
                "service_number": return_number,
                "origin_code": destination,
                "origin_city": destination_city,
                "destination_code": origin,
                "destination_city": origin_city,
                "departure_local": _short_datetime(return_date),
                "arrival_local": _short_datetime(return_date + timedelta(hours=7)),
                "status": "scheduled",
                "status_label": "Monitored",
            },
        ],
        "simulation": {
            "case_id": case["case_id"],
            "scenario_class": case["scenario_class"],
            "scenario_label": _scenario_label(case["scenario_class"]),
            "event_type": case["event_type"],
            "event_label": event_label,
            "expected_eligibility": case["expected_eligibility"],
            "language": case["language"],
            "user_query": case["user_query"],
            "dataset_size": len(synthetic_cases()),
            "product_options": (
                public_product_options()
                if "exact_card_product" in case["expected_missing_documents"]
                else []
            ),
        },
        "disruption": None,
    }

    if disruption_detected:
        duration = _duration_label(int(case["incident_duration_minutes"]))
        disruption = {
            "event_id": f"EVT-{case['case_id']}",
            "event_type": case["event_type"],
            "severity": "attention",
            "headline": EVENT_HEADLINES.get(case["event_type"], "Your journey needs attention"),
            "summary": _event_summary(case, service_number, origin, destination, duration),
            "detected_at": _short_datetime(departure + timedelta(minutes=int(case["incident_duration_minutes"]))),
            "duration": duration,
            "location": destination_airport,
            "carrier_reference": f"SIM-{case['case_id'][-4:]}",
            "source": "Synthetic carrier and itinerary signal",
            "source_confidence": "Benchmark input",
        }
        trip["disruption"] = disruption
        trip["monitoring"] = {
            **trip["monitoring"],
            "status": "attention",
            "label": event_label,
            "last_checked": disruption["detected_at"],
        }
        affected_index = 1 if case["event_type"] == "hotel_issue" else 0
        trip["segments"][affected_index]["status"] = "attention"
        trip["segments"][affected_index]["status_label"] = event_label
    return trip


def recovery_case_from_synthetic(
    case: dict[str, Any],
    *,
    live_guidance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an instant expected result, or bind live model guidance to the same trip."""

    trip = trip_from_case(case, disruption_detected=True)
    disruption = trip["disruption"]
    if live_guidance is None:
        status, headline, summary, confidence = ELIGIBILITY_PRESENTATION[case["expected_eligibility"]]
        guidance = {
            "status": status,
            "status_title": STATUS_TITLES[status],
            "headline": headline,
            "summary": summary,
            "confidence": confidence,
            "policy_evidence": _policy_evidence(case["expected_chunk_ids"]),
            "next_steps": [
                {
                    "priority": index,
                    "title": str(action).rstrip("."),
                    "description": "Complete this step promptly and retain the resulting confirmation or receipt.",
                }
                for index, action in enumerate(case["expected_actions"], start=1)
            ],
            "missing_information": list(case["expected_missing_documents"]),
            "human_review_required": True,
            "safety_note": case["safety_note"],
            "trace": {
                "pipeline": ["synthetic_case", "expected_routing", "evidence_check"],
                "evaluation_source": "deterministic_benchmark",
                "rule_version": case["rule_version"],
            },
        }
        processing_mode = "synthetic_expected"
    else:
        guidance = live_guidance
        processing_mode = "live_llm_rag"

    claim_items = _claim_items(case)
    if live_guidance is not None:
        claim_items = _with_live_missing_items(
            claim_items, guidance.get("missing_information", [])
        )
    completed = sum(item["status"] == "complete" for item in claim_items)
    return {
        "case_id": case["case_id"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "processing_mode": processing_mode,
        "trip": trip,
        "disruption": disruption,
        "benefit_match": {
            "status": guidance["status"],
            "status_title": guidance["status_title"],
            "headline": guidance["headline"],
            "summary": guidance["summary"],
            "confidence": guidance["confidence"],
            "product_name": case["product_name"],
            "payment_verified": bool(case["origin_return_paid_with_card"]),
            "policy_evidence": guidance["policy_evidence"],
            "expected_eligibility": (
                case["expected_eligibility"] if live_guidance is None else None
            ),
            "reason_codes": case["expected_reason_codes"] if live_guidance is None else [],
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


def dataset_insights() -> dict[str, Any]:
    """Return evidence for the product-need story, derived from all benchmark rows."""

    cases = synthetic_cases()
    total = len(cases)
    outcomes = _counts(cases, "expected_eligibility")
    events = _counts(cases, "event_type")
    products = _counts(cases, "product_name")
    missing_documents = sum(bool(case["expected_missing_documents"]) for case in cases)
    non_straightforward = total - outcomes.get("potentially_eligible", 0)
    multilingual = sum(case["language"] != "en" for case in cases)
    return {
        "dataset_size": total,
        "synthetic": True,
        "source": "Journeyback deterministic benchmark v1",
        "headline_metrics": {
            "needs_explanation_or_triage": _metric(non_straightforward, total),
            "missing_key_documents": _metric(missing_documents, total),
            "non_english_cases": _metric(multilingual, total),
        },
        "outcomes": outcomes,
        "events": events,
        "products": products,
        "product_need": (
            "Travel disruption is rarely a one-step claim decision: customers need fast evidence capture, "
            "policy explanation and safe routing across products, events and languages."
        ),
    }


@lru_cache(maxsize=1)
def _knowledge_by_id() -> dict[str, dict[str, Any]]:
    return {chunk["chunk_id"]: chunk for chunk in KnowledgeBase.load().chunks}


def _policy_evidence(chunk_ids: list[str]) -> list[dict[str, Any]]:
    by_id = _knowledge_by_id()
    evidence: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        chunk = by_id.get(chunk_id)
        if chunk is None:
            continue
        evidence.append({
            "chunk_id": chunk_id,
            "source_id": chunk["source_id"],
            "section": chunk["section"],
            "pages": chunk["pages"],
            "url": chunk["url"],
            "citation": chunk["citation"],
            "excerpt": chunk["retrieval_text"][:350],
            "relevance": "Expected benchmark evidence",
        })
    return evidence


def _claim_items(case: dict[str, Any]) -> list[dict[str, str]]:
    required = set(case["expected_missing_documents"])
    items: list[dict[str, str]] = []
    for code, label, field, source in DOCUMENTS:
        relevant = bool(case.get(field)) or code in required
        if code == "pir":
            relevant = relevant or str(case["event_type"]).startswith("baggage")
        if not relevant:
            continue
        items.append({
            "code": code,
            "label": label,
            "status": "complete" if bool(case.get(field)) and code not in required else "required",
            "source": source if bool(case.get(field)) else "Not yet available",
        })
    if "exact_card_product" in required:
        items.append({
            "code": "exact_card_product",
            "label": "Exact American Express Card product",
            "status": "required",
            "source": "Confirm with Card Member Services",
        })
    return items or [{
        "code": "manual_review",
        "label": "Specialist case review",
        "status": "required",
        "source": "JourneyBack assistance team",
    }]


def _with_live_missing_items(
    claim_items: list[dict[str, str]], missing_information: Any
) -> list[dict[str, str]]:
    """Turn new model-identified gaps into actionable upload controls."""

    if not isinstance(missing_information, list):
        return claim_items
    existing_text = " ".join(item["label"].lower() for item in claim_items)
    result = list(claim_items)
    dynamic_index = 1
    for value in missing_information:
        label = str(value).strip()
        if not label or label.lower() in existing_text:
            continue
        result.append({
            "code": f"llm_required_{dynamic_index}",
            "label": label,
            "status": "required",
            "source": "Requested by live policy analysis",
        })
        existing_text += f" {label.lower()}"
        dynamic_index += 1
    return result


def _event_summary(
    case: dict[str, Any], service_number: str, origin: str, destination: str, duration: str
) -> str:
    event = EVENT_LABELS.get(case["event_type"], "Travel disruption")
    return (
        f"A synthetic monitoring signal reports {event.lower()} for {service_number} "
        f"from {origin} to {destination}. The recorded duration is {duration}."
    )


def _scenario_label(value: str) -> str:
    return {
        "eligible_complete": "Potential match · evidence complete",
        "ineligible_rule": "Policy condition not met",
        "insufficient_evidence": "Evidence gap",
        "boundary_manual_review": "Policy boundary",
        "unsupported_or_product_unknown": "Product needs confirmation",
    }.get(value, value.replace("_", " ").title())


def _metric(count: int, total: int) -> dict[str, float | int]:
    return {"count": count, "percent": round(100 * count / total, 1)}


def _counts(cases: tuple[dict[str, Any], ...], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        value = str(case[key])
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _short_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %b, %H:%M UTC")


def _short_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %b")


def _date_range(start: datetime, end: datetime) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {start.strftime('%B %Y')}"
    return f"{start.strftime('%d %b')}–{end.strftime('%d %b %Y')}"


def _duration_label(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours} hr {remainder} min"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{minutes} minutes"


def _age_band(age: int) -> str:
    lower = age // 10 * 10
    return f"{lower}s"
