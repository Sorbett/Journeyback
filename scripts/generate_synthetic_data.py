#!/usr/bin/env python3
"""Generate a deterministic, policy-grounded Journeyback synthetic benchmark."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = PROJECT_ROOT / "data" / "knowledge_base"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "synthetic"
SEED = 20260811
CASE_COUNT = 600
RULE_VERSION = "journeyback-synthetic-rules-v1.0"

SCENARIO_COUNTS = {
    "eligible_complete": 180,
    "ineligible_rule": 150,
    "insufficient_evidence": 120,
    "boundary_manual_review": 90,
    "unsupported_or_product_unknown": 60,
}

SPLIT_BY_SCENARIO = {
    "eligible_complete": {"development": 108, "validation": 36, "test": 36},
    "ineligible_rule": {"development": 90, "validation": 30, "test": 30},
    "insufficient_evidence": {"development": 72, "validation": 24, "test": 24},
    "boundary_manual_review": {"development": 54, "validation": 18, "test": 18},
    "unsupported_or_product_unknown": {"development": 36, "validation": 12, "test": 12},
}

PRODUCT_COUNTS = {
    "SG_PLATINUM_CHARGE": 150,
    "SG_PLATINUM_RESERVE": 105,
    "SG_KRISFLYER_ASCEND": 105,
    "SG_TRUE_CASHBACK": 90,
    "SG_MY_TRAVEL_INSURANCE": 90,
    "SG_PLATINUM_CREDIT_UNCOVERED": 30,
    "UNKNOWN_PRODUCT": 30,
}

EVALUATION_WEIGHTS = [
    {
        "component": "eligibility_correctness",
        "weight": 30,
        "definition": "Correctly separates potentially eligible, unlikely, insufficient-information and manual-review cases.",
    },
    {
        "component": "product_policy_binding",
        "weight": 20,
        "definition": "Uses only the policy for the resolved Singapore product and never mixes thresholds or limits.",
    },
    {
        "component": "evidence_completeness",
        "weight": 15,
        "definition": "Identifies the missing ticket, carrier confirmation, PIR, receipts or certificate.",
    },
    {
        "component": "action_relevance",
        "weight": 15,
        "definition": "Recommends practical next actions appropriate to the incident and evidence state.",
    },
    {
        "component": "citation_grounding",
        "weight": 10,
        "definition": "Cites a matching authoritative source and policy chunk when making a benefit statement.",
    },
    {
        "component": "safety_and_calibration",
        "weight": 10,
        "definition": "Does not promise payment; exposes uncertainty and routes conflicts or stale versions to human review.",
    },
]

PRODUCT_RULES: dict[str, dict[str, Any]] = {
    "SG_PLATINUM_CHARGE": {
        "name": "The Platinum Card",
        "source_id": "POL-SG-PLATINUM-2021-06",
        "eligibility_chunk": "POL-SG-PLATINUM-ELIGIBILITY",
        "claims_chunk": "POL-SG-PLATINUM-CLAIMS",
        "exclusion_chunk": "POL-SG-PLATINUM-INCONVENIENCE-EXCLUSIONS",
        "payment_required": True,
        "claim_deadline_days": 30,
        "events": {
            "flight_delay": {
                "threshold_minutes": 240,
                "individual_limit": 400,
                "family_limit": 800,
                "chunk_id": "POL-SG-PLATINUM-TRAVEL-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "missed_connection": {
                "threshold_minutes": 240,
                "individual_limit": 400,
                "family_limit": 800,
                "chunk_id": "POL-SG-PLATINUM-TRAVEL-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "flight_cancellation": {
                "threshold_minutes": 240,
                "individual_limit": 400,
                "family_limit": 800,
                "chunk_id": "POL-SG-PLATINUM-TRAVEL-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "baggage_delay": {
                "threshold_minutes": 240,
                "individual_limit": 400,
                "family_limit": 800,
                "extended_threshold_minutes": 2880,
                "extended_individual_limit": 800,
                "extended_family_limit": 1600,
                "chunk_id": "POL-SG-PLATINUM-BAGGAGE",
                "required_documents": ["flight_ticket", "pir", "receipts"],
            },
        },
    },
    "SG_PLATINUM_RESERVE": {
        "name": "Platinum Reserve Credit Card",
        "source_id": "POL-SG-PLATINUM-RESERVE",
        "eligibility_chunk": "POL-SG-PLATINUM-RESERVE-ELIGIBILITY",
        "claims_chunk": "POL-SG-PLATINUM-RESERVE-CLAIMS",
        "exclusion_chunk": "POL-SG-PLATINUM-RESERVE-EXCLUSIONS",
        "payment_required": True,
        "claim_deadline_days": 30,
        "events": {
            "missed_connection": {
                "threshold_minutes": 240,
                "individual_limit": 200,
                "family_limit": 400,
                "chunk_id": "POL-SG-PLATINUM-RESERVE-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "baggage_delay": {
                "threshold_minutes": 360,
                "individual_limit": 200,
                "family_limit": 400,
                "chunk_id": "POL-SG-PLATINUM-RESERVE-INCONVENIENCE",
                "required_documents": ["flight_ticket", "pir", "receipts"],
            },
            "baggage_loss": {
                "threshold_minutes": 2880,
                "individual_limit": 500,
                "family_limit": 1000,
                "chunk_id": "POL-SG-PLATINUM-RESERVE-INCONVENIENCE",
                "required_documents": ["flight_ticket", "pir", "receipts"],
            },
        },
    },
    "SG_KRISFLYER_ASCEND": {
        "name": "KrisFlyer Ascend Credit Card",
        "source_id": "POL-SG-KF-ASCEND-2021-08",
        "eligibility_chunk": "POL-SG-KF-ASCEND-ELIGIBILITY",
        "claims_chunk": "POL-SG-KF-ASCEND-CLAIMS",
        "exclusion_chunk": "POL-SG-KF-ASCEND-EXCLUSIONS",
        "payment_required": True,
        "expense_card_charge_required": True,
        "claim_deadline_days": 30,
        "events": {
            "flight_delay": {
                "threshold_minutes": 240,
                "individual_limit": 200,
                "family_limit": 400,
                "chunk_id": "POL-SG-KF-ASCEND-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "missed_connection": {
                "threshold_minutes": 240,
                "individual_limit": 200,
                "family_limit": 400,
                "chunk_id": "POL-SG-KF-ASCEND-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "baggage_delay": {
                "threshold_minutes": 360,
                "individual_limit": 200,
                "family_limit": 400,
                "extended_threshold_minutes": 2880,
                "extended_individual_limit": 700,
                "extended_family_limit": 1400,
                "chunk_id": "POL-SG-KF-ASCEND-INCONVENIENCE",
                "required_documents": ["flight_ticket", "pir", "receipts"],
            },
        },
    },
    "SG_TRUE_CASHBACK": {
        "name": "True Cashback Card",
        "source_id": "POL-SG-TRUE-CASHBACK-2021-04",
        "eligibility_chunk": "POL-SG-TRUE-CASHBACK-ELIGIBILITY",
        "claims_chunk": "POL-SG-TRUE-CASHBACK-CLAIMS",
        "exclusion_chunk": "POL-SG-TRUE-CASHBACK-EXCLUSIONS",
        "payment_required": True,
        "claim_deadline_days": 30,
        "events": {
            "missed_connection": {
                "threshold_minutes": 240,
                "individual_limit": 200,
                "family_limit": 400,
                "chunk_id": "POL-SG-TRUE-CASHBACK-INCONVENIENCE",
                "required_documents": ["flight_ticket", "carrier_confirmation", "receipts"],
            },
            "baggage_delay": {
                "threshold_minutes": 360,
                "individual_limit": 200,
                "family_limit": 400,
                "chunk_id": "POL-SG-TRUE-CASHBACK-INCONVENIENCE",
                "required_documents": ["flight_ticket", "pir", "receipts"],
            },
            "baggage_loss": {
                "threshold_minutes": 2880,
                "individual_limit": 500,
                "family_limit": 1000,
                "chunk_id": "POL-SG-TRUE-CASHBACK-INCONVENIENCE",
                "required_documents": ["flight_ticket", "pir", "receipts"],
            },
        },
    },
    "SG_MY_TRAVEL_INSURANCE": {
        "name": "My Travel Insurance",
        "source_id": "POL-SG-MY-TRAVEL-2021-12",
        "eligibility_chunk": "POL-SG-MY-TRAVEL-PRODUCT-BOUNDARY",
        "claims_chunk": "POL-SG-MY-TRAVEL-PRODUCT-BOUNDARY",
        "exclusion_chunk": None,
        "payment_required": False,
        "claim_deadline_days": None,
        "events": {
            "flight_delay": {
                "threshold_minutes": 360,
                "individual_limit": None,
                "family_limit": None,
                "chunk_id": "POL-SG-MY-TRAVEL-DELAY",
                "required_documents": ["flight_ticket", "carrier_confirmation", "policy_certificate"],
            },
            "missed_connection": {
                "threshold_minutes": 360,
                "individual_limit": None,
                "family_limit": None,
                "chunk_id": "POL-SG-MY-TRAVEL-MISCONNECTION",
                "required_documents": ["flight_ticket", "carrier_confirmation", "policy_certificate"],
            },
        },
    },
}

DOCUMENT_FIELDS = {
    "flight_ticket": "has_flight_ticket",
    "carrier_confirmation": "has_carrier_confirmation",
    "pir": "has_pir",
    "receipts": "has_receipts",
    "policy_certificate": "has_policy_certificate",
    "medical_certificate": "has_medical_certificate",
}

EVENT_DESCRIPTIONS = {
    "flight_delay": ("航班延误", "flight delay"),
    "missed_connection": ("错过转机", "missed connection"),
    "flight_cancellation": ("航班取消且暂时没有替代航班", "flight cancellation with no prompt alternative"),
    "baggage_delay": ("托运行李延误", "checked-baggage delay"),
    "baggage_loss": ("托运行李超过48小时仍未送达", "checked baggage still missing after 48 hours"),
    "card_loss": ("境外遗失信用卡", "Card lost overseas"),
    "hotel_issue": ("酒店预订出现问题", "hotel booking issue"),
}

AIRPORTS = ["BKK", "DPS", "HKG", "ICN", "LHR", "NRT", "SYD"]
BOOKING_CHANNELS = ["amex_travel", "direct_airline", "online_travel_agent"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_schema() -> dict[str, Any]:
    required = [
        "case_id", "split", "synthetic", "seed", "market", "language", "scenario_class",
        "difficulty", "product_code", "product_name", "product_resolution_status", "event_type",
        "origin_airport", "destination_airport", "scheduled_departure_utc", "incident_duration_minutes",
        "origin_return_paid_with_card", "expense_charged_to_card", "claim_notice_days", "user_query",
        "expected_eligibility", "expected_routing", "expected_missing_documents", "expected_reason_codes",
        "expected_actions", "expected_source_ids", "expected_chunk_ids", "human_review_required",
        "expected_payout_sgd", "safety_note", "rule_version", "content_hash",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://journeyback.local/schemas/synthetic-case-v1.json",
        "title": "Journeyback synthetic travel-disruption case",
        "type": "object",
        "required": required,
        "properties": {
            "case_id": {"type": "string", "pattern": "^JB-SYN-[0-9]{4}$"},
            "split": {"enum": ["development", "validation", "test"]},
            "synthetic": {"const": True},
            "seed": {"type": "integer"},
            "market": {"type": "string"},
            "language": {"enum": ["zh", "en"]},
            "scenario_class": {"enum": list(SCENARIO_COUNTS)},
            "difficulty": {"enum": ["standard", "hard", "edge"]},
            "product_code": {"type": "string"},
            "product_name": {"type": "string"},
            "product_resolution_status": {"enum": ["resolved", "uncovered_product", "unknown"]},
            "event_type": {"type": "string"},
            "origin_airport": {"type": "string"},
            "destination_airport": {"type": "string"},
            "scheduled_departure_utc": {"type": "string", "format": "date-time"},
            "incident_duration_minutes": {"type": "integer", "minimum": 0},
            "origin_return_paid_with_card": {"type": "boolean"},
            "expense_charged_to_card": {"type": "boolean"},
            "claim_notice_days": {"type": "integer", "minimum": 0},
            "user_query": {"type": "string", "minLength": 20},
            "expected_eligibility": {
                "enum": ["potentially_eligible", "unlikely_eligible", "insufficient_information", "manual_review_required", "out_of_scope"]
            },
            "expected_routing": {"type": "string"},
            "expected_missing_documents": {"type": "array", "items": {"type": "string"}},
            "expected_reason_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "expected_actions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "expected_source_ids": {"type": "array", "items": {"type": "string"}},
            "expected_chunk_ids": {"type": "array", "items": {"type": "string"}},
            "human_review_required": {"const": True},
            "reference_limit_sgd": {"type": ["integer", "null"], "minimum": 0},
            "expected_payout_sgd": {"type": "null"},
            "safety_note": {"type": "string"},
            "rule_version": {"const": RULE_VERSION},
            "content_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        },
        "additionalProperties": True,
    }


def make_split_pool(scenario_class: str, rng: random.Random) -> list[str]:
    pool = [split for split, count in SPLIT_BY_SCENARIO[scenario_class].items() for _ in range(count)]
    rng.shuffle(pool)
    return pool


def set_document(case: dict[str, Any], document: str, value: bool) -> None:
    case[DOCUMENT_FIELDS[document]] = value


def reference_limit(rule: dict[str, Any], duration: int, family_size: int) -> int | None:
    if rule.get("individual_limit") is None:
        return None
    is_family = family_size > 1
    if rule.get("extended_threshold_minutes") and duration >= rule["extended_threshold_minutes"]:
        return rule["extended_family_limit"] if is_family else rule["extended_individual_limit"]
    return rule["family_limit"] if is_family else rule["individual_limit"]


def event_actions(event_type: str) -> list[str]:
    if event_type in {"baggage_delay", "baggage_loss"}:
        return [
            "Obtain a Property Irregularity Report from the carrier.",
            "Keep receipts for necessary and reasonable purchases.",
            "Track the baggage return time and retain carrier correspondence.",
        ]
    if event_type in {"flight_delay", "missed_connection", "flight_cancellation"}:
        return [
            "Request written disruption and alternative-flight confirmation from the carrier.",
            "Keep the ticket, itinerary and itemised receipts.",
            "Compare available rebooking, accommodation and ground-transport options.",
        ]
    if event_type == "card_loss":
        return ["Contact Amex Card Assistance immediately.", "Block or replace the Card through an authorised channel."]
    return ["Contact the booking provider and retain written confirmation.", "Route the case to a human support specialist."]


def build_query(case: dict[str, Any]) -> str:
    zh_event, en_event = EVENT_DESCRIPTIONS[case["event_type"]]
    hours = case["incident_duration_minutes"] / 60
    duration = f"{hours:g}"
    if case["language"] == "zh":
        if case["product_resolution_status"] != "resolved":
            return f"我在新加坡持有一张Amex卡，但不确定具体卡种，现在遇到{zh_event}，已经{duration}小时，应该怎么办？"
        return (
            f"我使用{case['product_name']}出行，现在遇到{zh_event}，已经{duration}小时。"
            f"我{'有' if case['has_carrier_confirmation'] else '没有'}航空公司书面证明，下一步应该怎么处理？"
        )
    if case["product_resolution_status"] != "resolved":
        return f"I hold an Amex Card in Singapore but cannot identify the exact product. I have experienced {en_event}; the disruption has lasted {duration} hours. What should I do?"
    return (
        f"I am travelling with {case['product_name']} and have experienced {en_event}; the disruption has lasted {duration} hours. "
        f"I {'have' if case['has_carrier_confirmation'] else 'do not have'} written carrier confirmation. What should I do next?"
    )


def build_known_case(
    *,
    case_id: str,
    split: str,
    scenario_class: str,
    product_code: str,
    rng: random.Random,
) -> dict[str, Any]:
    product = PRODUCT_RULES[product_code]
    event_type = rng.choice(sorted(product["events"]))
    rule = product["events"][event_type]
    threshold = rule["threshold_minutes"]
    destination = rng.choice(AIRPORTS)
    scheduled = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc) + timedelta(
        days=rng.randrange(90), hours=rng.randrange(18)
    )
    family_size = rng.choices([1, 2, 3, 4], weights=[55, 25, 15, 5], k=1)[0]
    traveler_type = rng.choices(["cardmember", "spouse", "dependent_child"], weights=[75, 18, 7], k=1)[0]
    traveler_age = rng.randint(23, 75) if traveler_type != "dependent_child" else rng.randint(8, 22)
    language = "zh" if rng.random() < 0.6 else "en"

    case: dict[str, Any] = {
        "case_id": case_id,
        "split": split,
        "synthetic": True,
        "seed": SEED,
        "market": "SG",
        "language": language,
        "scenario_class": scenario_class,
        "difficulty": "standard",
        "product_code": product_code,
        "product_name": product["name"],
        "product_resolution_status": "resolved",
        "event_type": event_type,
        "traveler_type": traveler_type,
        "traveler_age": traveler_age,
        "family_size": family_size,
        "travelling_with_cardmember": traveler_type == "cardmember" or rng.random() < 0.9,
        "route_phase": rng.choice(["outbound", "mid_trip", "return"]),
        "is_final_return_leg": False,
        "trip_duration_days": rng.randint(2, 30),
        "booking_channel": rng.choice(BOOKING_CHANNELS),
        "origin_airport": "SIN",
        "destination_airport": destination,
        "carrier_code": f"CARRIER-{rng.choice('ABCDE')}",
        "scheduled_departure_utc": scheduled.isoformat().replace("+00:00", "Z"),
        "incident_duration_minutes": threshold + rng.choice([30, 60, 120, 360, 720]),
        "alternative_offered": False,
        "alternative_refused": False,
        "origin_return_paid_with_card": True,
        "expense_charged_to_card": True,
        "expense_category": "essential_items" if event_type.startswith("baggage") else "travel_meals_or_accommodation",
        "expense_sgd": rng.randint(25, 520),
        "claim_notice_days": rng.randint(1, 25),
        "has_flight_ticket": True,
        "has_carrier_confirmation": True,
        "has_pir": True,
        "has_receipts": True,
        "has_policy_certificate": True,
        "has_medical_certificate": False,
        "expected_missing_documents": [],
        "expected_source_ids": [product["source_id"]],
        "expected_chunk_ids": list(
            dict.fromkeys(
                [
                    product["eligibility_chunk"],
                    rule["chunk_id"],
                    product["claims_chunk"],
                ]
            )
        ),
        "expected_actions": event_actions(event_type),
        "human_review_required": True,
        "expected_payout_sgd": None,
        "safety_note": "Synthetic benchmark only. Explain likely applicability, cite the policy and require human review; never promise coverage or payment.",
        "rule_version": RULE_VERSION,
    }

    if scenario_class == "eligible_complete":
        case["expected_eligibility"] = "potentially_eligible"
        case["expected_routing"] = "policy_explanation_with_human_review"
        eligibility_reason = "payment_condition_met" if product.get("payment_required") else "policy_certificate_available"
        case["expected_reason_codes"] = ["threshold_met", eligibility_reason, "evidence_complete"]

    elif scenario_class == "insufficient_evidence":
        case["difficulty"] = "hard"
        removable = list(rule["required_documents"])
        missing = rng.sample(removable, k=rng.randint(1, min(2, len(removable))))
        for document in missing:
            set_document(case, document, False)
        case["expected_missing_documents"] = sorted(missing)
        case["expected_eligibility"] = "insufficient_information"
        case["expected_routing"] = "request_more_information"
        case["expected_reason_codes"] = ["threshold_met", "required_evidence_missing"]

    elif scenario_class == "boundary_manual_review":
        case["difficulty"] = "edge"
        case["incident_duration_minutes"] = threshold + rng.choice([-1, 0, 1])
        case["claim_notice_days"] = 30 if product.get("claim_deadline_days") else rng.randint(1, 25)
        case["expected_eligibility"] = "manual_review_required"
        case["expected_routing"] = "manual_policy_review"
        case["expected_reason_codes"] = ["threshold_boundary", "exact_event_timing_required"]

    elif scenario_class == "ineligible_rule":
        failure_modes = ["below_threshold"]
        if product.get("payment_required"):
            failure_modes.append("payment_condition_failed")
        if product.get("expense_card_charge_required"):
            failure_modes.append("expense_not_charged_to_card")
        if event_type.startswith("baggage") and product_code in {
            "SG_PLATINUM_CHARGE", "SG_PLATINUM_RESERVE", "SG_KRISFLYER_ASCEND"
        }:
            failure_modes.append("final_return_leg_baggage")
        if not event_type.startswith("baggage") and product_code != "SG_MY_TRAVEL_INSURANCE":
            failure_modes.append("alternative_refused")
        if product.get("claim_deadline_days"):
            failure_modes.append("claim_notified_late")
        if event_type.startswith("baggage") and product_code == "SG_PLATINUM_CHARGE":
            failure_modes.append("nonessential_purchase")

        failure = rng.choice(failure_modes)
        if failure == "below_threshold":
            case["incident_duration_minutes"] = max(0, threshold - rng.choice([15, 60, 120]))
        elif failure == "payment_condition_failed":
            case["origin_return_paid_with_card"] = False
        elif failure == "expense_not_charged_to_card":
            case["expense_charged_to_card"] = False
        elif failure == "final_return_leg_baggage":
            case["route_phase"] = "return"
            case["is_final_return_leg"] = True
        elif failure == "alternative_refused":
            case["alternative_offered"] = True
            case["alternative_refused"] = True
        elif failure == "claim_notified_late":
            case["claim_notice_days"] = rng.randint(31, 55)
        elif failure == "nonessential_purchase":
            case["expense_category"] = "nonessential_luxury_item"

        case["expected_eligibility"] = "unlikely_eligible"
        case["expected_routing"] = "ineligible_explanation_with_human_review"
        case["expected_reason_codes"] = [failure]
        if product.get("exclusion_chunk") and failure in {
            "final_return_leg_baggage", "alternative_refused", "nonessential_purchase"
        }:
            case["expected_chunk_ids"].append(product["exclusion_chunk"])

    else:
        raise ValueError(f"Unsupported known scenario class: {scenario_class}")

    case["reference_limit_sgd"] = (
        reference_limit(rule, case["incident_duration_minutes"], family_size)
        if case["expected_eligibility"] in {"potentially_eligible", "insufficient_information"}
        else None
    )
    case["user_query"] = build_query(case)
    return case


def build_out_of_scope_case(*, case_id: str, split: str, product_code: str, rng: random.Random) -> dict[str, Any]:
    event_type = rng.choice(["flight_delay", "card_loss", "hotel_issue"])
    scheduled = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc) + timedelta(days=rng.randrange(90))
    product_name = "Platinum Credit Card (not yet covered by this corpus)" if product_code != "UNKNOWN_PRODUCT" else "Unknown Amex Card"
    case: dict[str, Any] = {
        "case_id": case_id,
        "split": split,
        "synthetic": True,
        "seed": SEED,
        "market": "SG",
        "language": "zh" if rng.random() < 0.6 else "en",
        "scenario_class": "unsupported_or_product_unknown",
        "difficulty": "edge",
        "product_code": product_code,
        "product_name": product_name,
        "product_resolution_status": "unknown" if product_code == "UNKNOWN_PRODUCT" else "uncovered_product",
        "event_type": event_type,
        "traveler_type": "cardmember",
        "traveler_age": rng.randint(23, 70),
        "family_size": rng.choice([1, 2]),
        "travelling_with_cardmember": True,
        "route_phase": rng.choice(["outbound", "mid_trip", "return"]),
        "is_final_return_leg": False,
        "trip_duration_days": rng.randint(2, 21),
        "booking_channel": rng.choice(BOOKING_CHANNELS),
        "origin_airport": "SIN",
        "destination_airport": rng.choice(AIRPORTS),
        "carrier_code": f"CARRIER-{rng.choice('ABCDE')}",
        "scheduled_departure_utc": scheduled.isoformat().replace("+00:00", "Z"),
        "incident_duration_minutes": rng.choice([120, 240, 360, 720]),
        "alternative_offered": False,
        "alternative_refused": False,
        "origin_return_paid_with_card": rng.choice([True, False]),
        "expense_charged_to_card": rng.choice([True, False]),
        "expense_category": "unknown",
        "expense_sgd": rng.randint(0, 400),
        "claim_notice_days": rng.randint(1, 25),
        "has_flight_ticket": rng.choice([True, False]),
        "has_carrier_confirmation": rng.choice([True, False]),
        "has_pir": False,
        "has_receipts": rng.choice([True, False]),
        "has_policy_certificate": False,
        "has_medical_certificate": False,
        "expected_eligibility": "out_of_scope",
        "expected_routing": "out_of_scope_handoff",
        "reference_limit_sgd": None,
        "expected_payout_sgd": None,
        "expected_missing_documents": ["exact_card_product"],
        "expected_reason_codes": ["product_not_resolved_or_not_covered"],
        "expected_actions": event_actions(event_type) + ["Resolve the exact Card product before giving benefit-specific guidance."],
        "expected_source_ids": ["SG-AMEX-CARD-ASSIST"] if event_type == "card_loss" else [],
        "expected_chunk_ids": [],
        "human_review_required": True,
        "safety_note": "Synthetic benchmark only. Do not infer benefits for an unknown or uncovered product; route to human review.",
        "rule_version": RULE_VERSION,
    }
    case["user_query"] = build_query(case)
    return case


def add_hash(case: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    case["content_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return case


def generate_cases() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    known_products = [
        product_code
        for product_code, count in PRODUCT_COUNTS.items()
        if product_code in PRODUCT_RULES
        for _ in range(count)
    ]
    rng.shuffle(known_products)
    out_products = ["SG_PLATINUM_CREDIT_UNCOVERED"] * 30 + ["UNKNOWN_PRODUCT"] * 30
    rng.shuffle(out_products)

    cases: list[dict[str, Any]] = []
    known_index = 0
    out_index = 0
    case_number = 1
    for scenario_class, count in SCENARIO_COUNTS.items():
        split_pool = make_split_pool(scenario_class, rng)
        for _ in range(count):
            case_id = f"JB-SYN-{case_number:04d}"
            split = split_pool.pop()
            if scenario_class == "unsupported_or_product_unknown":
                case = build_out_of_scope_case(
                    case_id=case_id,
                    split=split,
                    product_code=out_products[out_index],
                    rng=rng,
                )
                out_index += 1
            else:
                case = build_known_case(
                    case_id=case_id,
                    split=split,
                    scenario_class=scenario_class,
                    product_code=known_products[known_index],
                    rng=rng,
                )
                known_index += 1
            cases.append(add_hash(case))
            case_number += 1
    return cases


def validate_cases(cases: list[dict[str, Any]], schema: dict[str, Any]) -> dict[str, bool]:
    kb_chunks = [json.loads(line) for line in (KB_ROOT / "rag" / "knowledge_base.jsonl").read_text(encoding="utf-8").splitlines() if line]
    kb_chunk_ids = {chunk["chunk_id"] for chunk in kb_chunks}
    kb_source_ids = {
        source["source_id"]
        for source in json.loads((KB_ROOT / "normalized" / "sources.json").read_text(encoding="utf-8"))
    }
    required_fields = set(schema["required"])
    pii_terms = {"name", "email", "phone", "passport", "address", "card_number", "account_number"}
    scenario_counts = Counter(case["scenario_class"] for case in cases)
    split_counts = Counter(case["split"] for case in cases)
    product_counts = Counter(case["product_code"] for case in cases)
    expected_split_counts = {
        split: sum(plan[split] for plan in SPLIT_BY_SCENARIO.values())
        for split in ("development", "validation", "test")
    }
    checks = {
        "case_count_exactly_600": len(cases) == CASE_COUNT,
        "case_ids_unique": len({case["case_id"] for case in cases}) == len(cases),
        "content_hashes_unique": len({case["content_hash"] for case in cases}) == len(cases),
        "all_required_fields_present": all(required_fields <= set(case) for case in cases),
        "scenario_allocation_exact": dict(scenario_counts) == SCENARIO_COUNTS,
        "split_allocation_exact": dict(split_counts) == expected_split_counts,
        "product_allocation_exact": dict(product_counts) == PRODUCT_COUNTS,
        "all_cases_marked_synthetic": all(case["synthetic"] is True for case in cases),
        "no_direct_pii_fields": all(not (set(case) & pii_terms) for case in cases),
        "all_expected_sources_exist": all(set(case["expected_source_ids"]) <= kb_source_ids for case in cases),
        "all_expected_chunks_exist": all(set(case["expected_chunk_ids"]) <= kb_chunk_ids for case in cases),
        "eligible_cases_have_complete_evidence": all(
            not case["expected_missing_documents"]
            for case in cases
            if case["scenario_class"] == "eligible_complete"
        ),
        "insufficient_cases_have_missing_evidence": all(
            bool(case["expected_missing_documents"])
            for case in cases
            if case["scenario_class"] == "insufficient_evidence"
        ),
        "out_of_scope_cases_have_no_limit": all(
            case["reference_limit_sgd"] is None
            for case in cases
            if case["scenario_class"] == "unsupported_or_product_unknown"
        ),
        "no_case_contains_expected_payout": all(case["expected_payout_sgd"] is None for case in cases),
        "all_cases_require_human_review": all(case["human_review_required"] is True for case in cases),
        "evaluation_weights_total_100": sum(item["weight"] for item in EVALUATION_WEIGHTS) == 100,
    }
    return checks


def main() -> None:
    schema = build_schema()
    cases = generate_cases()
    checks = validate_cases(cases, schema)
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Synthetic data quality checks failed: {failed}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_ROOT / "journeyback_cases.jsonl").open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")

    evaluation_framework = {
        "schema_version": "1.0",
        "total_points": 100,
        "components": EVALUATION_WEIGHTS,
        "hard_caps": [
            {
                "condition": "A response mixes a threshold or limit from another Card product.",
                "maximum_total_score": 40,
            },
            {
                "condition": "A response promises claim approval or a payout.",
                "maximum_total_score": 40,
            },
            {
                "condition": "An unknown, conflicting or uncovered product is not routed to human review.",
                "maximum_total_score": 60,
            },
        ],
        "case_score_formula": "sum(component_score_0_to_1 * component_weight), then apply the lowest relevant hard cap",
    }
    write_json(OUTPUT_ROOT / "case_schema.json", schema)
    write_json(OUTPUT_ROOT / "evaluation_framework.json", evaluation_framework)

    quality_report = {
        "schema_version": "1.0",
        "generated_for": "Journeyback MVP evaluation and demonstration",
        "seed": SEED,
        "case_count": len(cases),
        "scenario_distribution": dict(Counter(case["scenario_class"] for case in cases)),
        "split_distribution": dict(Counter(case["split"] for case in cases)),
        "product_distribution": dict(Counter(case["product_code"] for case in cases)),
        "event_distribution": dict(Counter(case["event_type"] for case in cases)),
        "eligibility_distribution": dict(Counter(case["expected_eligibility"] for case in cases)),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
        "quality_score": 100 if all(checks.values()) else 0,
        "limitations": [
            "All rows are synthetic and contain no real Card Member, booking or claim data.",
            "Labels are derived from the current public Singapore corpus and inherit its version limitations.",
            "Potential eligibility is not claim approval; every case requires human review.",
            "The dataset evaluates product binding, evidence collection and recovery guidance, not fraud propensity.",
        ],
    }
    write_json(OUTPUT_ROOT / "quality_report.json", quality_report)

    readme = """# Journeyback Synthetic Dataset v1

This folder contains 600 deterministic, fully synthetic travel-disruption cases grounded in the imported Singapore Amex public-policy corpus.

## Files

- `journeyback_cases.jsonl`: runtime and evaluation cases.
- `case_schema.json`: field contract.
- `evaluation_framework.json`: weighted 100-point system evaluation framework and hard safety caps.
- `quality_report.json`: exact distributions and automated validation results.

## Strict allocation

- 30% potentially eligible with complete evidence.
- 25% unlikely under a stated rule.
- 20% missing required evidence.
- 15% threshold or timing boundary cases.
- 10% unknown or currently uncovered products.
- Split: 60% development, 20% validation, 20% held-out test.

## Safety

Every record has `synthetic=true`, `expected_payout_sgd=null` and `human_review_required=true`. The labels support benchmarking and demonstration only; they do not approve insurance claims or promise coverage.

## Regenerate

```bash
python3 scripts/generate_synthetic_data.py
```
"""
    (OUTPUT_ROOT / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(quality_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
