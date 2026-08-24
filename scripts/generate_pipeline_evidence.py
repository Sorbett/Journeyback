#!/usr/bin/env python3
"""Generate deterministic TXT evidence packages from the synthetic benchmark."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "synthetic" / "journeyback_cases.jsonl"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "pipeline_test"
GOLDEN_CASE_ID = "JB-SYN-0331"
POST_CONFIRMATION_EVENT_EVIDENCE = {
    "flight_delay": ["flight_ticket", "carrier_confirmation", "receipts"],
}

CARRIERS = {
    "CARRIER-A": ("Singapore Airlines", "SQ"),
    "CARRIER-B": ("Cathay Pacific", "CX"),
    "CARRIER-C": ("Qantas", "QF"),
    "CARRIER-D": ("Thai Airways", "TG"),
    "CARRIER-E": ("Korean Air", "KE"),
}

FILE_NAMES = {
    "flight_ticket": "flight_ticket_and_itinerary.txt",
    "carrier_confirmation": "carrier_confirmation.txt",
    "pir": "property_irregularity_report.txt",
    "receipts": "itemised_expense_receipts.txt",
    "policy_certificate": "policy_certificate.txt",
}

EVIDENCE_NOTES = {
    "flight_ticket": "Verify the passenger, route, dates, ticket reference and recorded Card product.",
    "carrier_confirmation": "Verify the disruption type, duration and carrier operational record.",
    "pir": "Verify the baggage incident report and carrier tracing reference.",
    "receipts": "Verify the itemised disruption expense, amount and recorded payment method.",
    "policy_certificate": "Verify the named product and synthetic policy certificate reference.",
}


def main() -> None:
    cases = _load_cases()
    packages: list[dict[str, Any]] = []
    evidence_counts: Counter[str] = Counter()
    for case in cases:
        missing = [code for code in case["expected_missing_documents"] if code in FILE_NAMES]
        post_confirmation = (
            POST_CONFIRMATION_EVENT_EVIDENCE.get(case["event_type"])
            if "exact_card_product" in case["expected_missing_documents"]
            else None
        )
        if not missing and post_confirmation is None:
            continue
        evidence_codes = list(post_confirmation or missing)
        if case["case_id"] == GOLDEN_CASE_ID:
            evidence_codes = ["flight_ticket", "carrier_confirmation", "receipts"]
        package = _write_package(
            case,
            evidence_codes,
            product_bound_at_runtime=post_confirmation is not None,
        )
        package_summary = {
            "case_id": package["case_id"],
            "product_code": package["product_code"],
            "package_mode": package["package_mode"],
            "expected_missing_documents": package["expected_missing_documents"],
            "file_count": len(package["files"]),
        }
        if package.get("product_bound_at_runtime"):
            package_summary["product_bound_at_runtime"] = True
        packages.append(package_summary)
        evidence_counts.update(evidence_codes)

    index = {
        "schema_version": 1,
        "generation_version": "journeyback-evidence-v1.0",
        "source": "data/synthetic/journeyback_cases.jsonl",
        "package_count": len(packages),
        "file_count": sum(item["file_count"] for item in packages),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "packages": packages,
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Generated {index['package_count']} evidence packages "
        f"with {index['file_count']} files in {OUTPUT_ROOT}"
    )


def _load_cases() -> list[dict[str, Any]]:
    cases = [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(cases) != 600:
        raise ValueError(f"Expected 600 benchmark cases, found {len(cases)}")
    return cases


def _write_package(
    case: dict[str, Any],
    evidence_codes: list[str],
    *,
    product_bound_at_runtime: bool,
) -> dict[str, Any]:
    case_root = OUTPUT_ROOT / case["case_id"]
    case_root.mkdir(parents=True, exist_ok=True)
    document_case = dict(case)
    if product_bound_at_runtime:
        document_case["product_code"] = "{{PRODUCT_CODE}}"
        document_case["product_name"] = "{{PRODUCT_NAME}}"
    files: list[dict[str, Any]] = []
    for evidence_code in evidence_codes:
        file_name = FILE_NAMES[evidence_code]
        content = DOCUMENT_BUILDERS[evidence_code](document_case)
        path = case_root / file_name
        path.write_text(content, encoding="utf-8")
        raw = content.encode("utf-8")
        files.append({
            "evidence_code": evidence_code,
            "file_name": file_name,
            "mime_type": "text/plain",
            "evidence_note": EVIDENCE_NOTES[evidence_code],
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })

    manifest = {
        "schema_version": 1,
        "generation_version": "journeyback-evidence-v1.0",
        "case_id": case["case_id"],
        "product_code": case["product_code"],
        "product_name": case["product_name"],
        "source_case_hash": case["content_hash"],
        "package_mode": (
            "golden_path"
            if case["case_id"] == GOLDEN_CASE_ID
            else "post_product_confirmation"
            if product_bound_at_runtime
            else "missing_evidence"
        ),
        "expected_missing_documents": case["expected_missing_documents"],
        "files": files,
    }
    if product_bound_at_runtime:
        manifest["product_bound_at_runtime"] = True
    (case_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _header(case: dict[str, Any], document_type: str) -> list[str]:
    return [
        "JOURNEYBACK SYNTHETIC PIPELINE TEST DOCUMENT",
        "",
        f"CASE_ID: {case['case_id']}",
        f"DOCUMENT_TYPE: {document_type}",
        "DOCUMENT_STATUS: ISSUED",
        "SYNTHETIC_RECORD: YES",
    ]


def _flight(case: dict[str, Any]) -> tuple[str, str, str, str]:
    _, prefix = CARRIERS.get(case["carrier_code"], ("Partner airline", "JB"))
    number = 100 + int(case["case_id"][-4:]) % 800
    return (
        f"{prefix} {number}",
        f"{prefix} {number + 1}",
        case["origin_airport"],
        case["destination_airport"],
    )


def _format_utc(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")


def _bool(value: Any) -> str:
    return "YES" if bool(value) else "NO"


def _event(value: str) -> str:
    return value.replace("_", " ").upper()


def _flight_ticket(case: dict[str, Any]) -> str:
    outbound, returning, origin, destination = _flight(case)
    departure = datetime.fromisoformat(case["scheduled_departure_utc"].replace("Z", "+00:00"))
    return_date = departure + timedelta(days=int(case["trip_duration_days"]))
    lines = _header(case, "FLIGHT_TICKET_AND_ITINERARY") + [
        f"BOOKING_REFERENCE: JBX{case['case_id'][-4:]}",
        f"TICKET_NUMBER: SYN-{case['case_id'][-4:]}-001",
        f"PASSENGER: DEMO TRAVELLER {case['case_id'][-4:]}",
        f"TRAVELLER_TYPE: {_event(case['traveler_type'])}",
        f"PARTY_SIZE: {case['family_size']}",
        "",
        f"CARD_PRODUCT: {case['product_name'].upper()}",
        f"CARD_PRODUCT_CODE: {case['product_code']}",
        f"ROUND_TRIP_PAID_WITH_RECORDED_CARD: {_bool(case['origin_return_paid_with_card'])}",
        f"BOOKING_CHANNEL: {_event(case['booking_channel'])}",
        "",
        f"OUTBOUND_FLIGHT: {outbound}",
        f"OUTBOUND_ROUTE: {origin} TO {destination}",
        f"SCHEDULED_DEPARTURE_UTC: {_format_utc(case['scheduled_departure_utc'])}",
        f"RETURN_FLIGHT: {returning}",
        f"RETURN_ROUTE: {destination} TO {origin}",
        f"SCHEDULED_RETURN_UTC: {return_date.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"DISRUPTION_RECORDED: {_event(case['event_type'])}",
        f"RECORDED_DURATION_MINUTES: {case['incident_duration_minutes']}",
        "",
        "This record is entirely synthetic. It is not a real ticket, booking or payment record.",
    ]
    return "\n".join(lines) + "\n"


def _carrier_confirmation(case: dict[str, Any]) -> str:
    carrier_name, _ = CARRIERS.get(case["carrier_code"], ("Partner airline", "JB"))
    outbound, _, origin, destination = _flight(case)
    lines = _header(case, "CARRIER_WRITTEN_CONFIRMATION") + [
        f"CARRIER: {carrier_name.upper()}",
        f"SERVICE: {outbound}",
        f"ROUTE: {origin} TO {destination}",
        f"SCHEDULED_DEPARTURE_UTC: {_format_utc(case['scheduled_departure_utc'])}",
        "",
        f"EVENT: {_event(case['event_type'])}",
        f"DISRUPTION_DURATION_MINUTES: {case['incident_duration_minutes']}",
        f"ALTERNATIVE_OFFERED: {_bool(case['alternative_offered'])}",
        f"ALTERNATIVE_REFUSED: {_bool(case['alternative_refused'])}",
        "OPERATIONAL_RECORD_CONFIRMED: YES",
        "",
        "The carrier confirms that the event and duration above were recorded in its synthetic operational record.",
        "This document is entirely synthetic and is not real carrier correspondence.",
    ]
    return "\n".join(lines) + "\n"


def _pir(case: dict[str, Any]) -> str:
    carrier_name, _ = CARRIERS.get(case["carrier_code"], ("Partner airline", "JB"))
    outbound, _, origin, destination = _flight(case)
    lines = _header(case, "PROPERTY_IRREGULARITY_REPORT") + [
        f"PIR_REFERENCE: PIR-{case['case_id'][-4:]}-{destination}",
        f"PASSENGER: DEMO TRAVELLER {case['case_id'][-4:]}",
        f"CARRIER: {carrier_name.upper()}",
        f"SERVICE: {outbound}",
        f"ROUTE: {origin} TO {destination}",
        f"INCIDENT: {_event(case['event_type'])}",
        f"INCIDENT_REPORTED_AT_AIRPORT: {destination}",
        f"TRACING_STATUS: {'OPEN' if case['event_type'] == 'baggage_loss' else 'DELAYED BAG REGISTERED'}",
        "",
        "The baggage desk registered this synthetic property irregularity report for testing only.",
        "This is not a real airline baggage report.",
    ]
    return "\n".join(lines) + "\n"


def _receipts(case: dict[str, Any]) -> str:
    amount = float(case["expense_sgd"])
    lines = _header(case, "ITEMISED_EXPENSE_RECEIPTS") + [
        "CURRENCY: SGD",
        f"CARD_PRODUCT: {case['product_name'].upper()}",
        f"EXPENSE_CHARGED_TO_RECORDED_CARD: {_bool(case['expense_charged_to_card'])}",
        f"ITEM_1: {_event(case['expense_category'])} | SGD {amount:.2f}",
        f"TOTAL: SGD {amount:.2f}",
        f"RELATED_EVENT: {_event(case['event_type'])}",
        f"RELATED_EVENT_DURATION_MINUTES: {case['incident_duration_minutes']}",
        "",
        "The entry is synthetic and exists only to verify JourneyBack's evidence pipeline.",
    ]
    return "\n".join(lines) + "\n"


def _policy_certificate(case: dict[str, Any]) -> str:
    lines = _header(case, "POLICY_CERTIFICATE") + [
        f"CERTIFICATE_REFERENCE: CERT-{case['case_id'][-4:]}-{case['product_code']}",
        f"PRODUCT_NAME: {case['product_name'].upper()}",
        f"PRODUCT_CODE: {case['product_code']}",
        f"INSURED_TRAVELLER: DEMO TRAVELLER {case['case_id'][-4:]}",
        f"TRAVELLER_TYPE: {_event(case['traveler_type'])}",
        f"TRAVEL_PARTY_SIZE: {case['family_size']}",
        f"TRIP_START_UTC: {_format_utc(case['scheduled_departure_utc'])}",
        f"TRIP_DURATION_DAYS: {case['trip_duration_days']}",
        "CERTIFICATE_MATCHED_TO_SYNTHETIC_CASE: YES",
        "",
        "This certificate confirms only the synthetic product record. It does not approve coverage or payment.",
        "This is not a real insurance certificate.",
    ]
    return "\n".join(lines) + "\n"


DOCUMENT_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "flight_ticket": _flight_ticket,
    "carrier_confirmation": _carrier_confirmation,
    "pir": _pir,
    "receipts": _receipts,
    "policy_certificate": _policy_certificate,
}


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Evidence generation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
