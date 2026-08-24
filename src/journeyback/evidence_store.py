"""Local demo evidence storage and safe case enrichment for live reanalysis."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT


DEFAULT_UPLOAD_ROOT = PROJECT_ROOT / ".journeyback_uploads"
MAX_FILE_BYTES = 1_500_000

SUPPORTED_PRODUCTS: dict[str, str] = {
    "SG_PLATINUM_CHARGE": "The Platinum Card",
    "SG_PLATINUM_RESERVE": "Platinum Reserve Credit Card",
    "SG_KRISFLYER_ASCEND": "KrisFlyer Ascend Credit Card",
    "SG_TRUE_CASHBACK": "True Cashback Card",
    "SG_MY_TRAVEL_INSURANCE": "My Travel Insurance",
}

EVIDENCE_FIELDS = {
    "flight_ticket": "has_flight_ticket",
    "carrier_confirmation": "has_carrier_confirmation",
    "pir": "has_pir",
    "receipts": "has_receipts",
    "policy_certificate": "has_policy_certificate",
}

LLM_EVIDENCE_PREFIX = "llm_required_"

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
}


def public_product_options() -> list[dict[str, str]]:
    return [{"code": code, "name": name} for code, name in SUPPORTED_PRODUCTS.items()]


def save_evidence(
    *,
    case_id: str,
    evidence_code: str,
    file_name: str,
    mime_type: str,
    content_base64: str,
    evidence_note: str = "",
    upload_root: Path = DEFAULT_UPLOAD_ROOT,
) -> dict[str, Any]:
    """Validate and persist a user-selected demo document on the local server."""

    if evidence_code not in EVIDENCE_FIELDS and not evidence_code.startswith(LLM_EVIDENCE_PREFIX):
        raise ValueError("This evidence type cannot be uploaded.")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Upload a PDF, JPG, PNG or plain-text file.")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The uploaded file is not valid base64 data.") from exc
    if not content:
        raise ValueError("The uploaded file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("The uploaded file must be 1.5 MB or smaller.")
    note = evidence_note.strip()
    if len(note) > 500:
        raise ValueError("The evidence note must be 500 characters or fewer.")

    safe_case_id = _safe_token(case_id, fallback="case")
    safe_name = _safe_filename(file_name)
    digest = hashlib.sha256(content).hexdigest()
    upload_id = f"UP-{digest[:16]}"
    case_root = upload_root / safe_case_id
    case_root.mkdir(parents=True, exist_ok=True)
    stored_name = f"{upload_id}_{safe_name}"
    stored_path = case_root / stored_name
    stored_path.write_bytes(content)
    metadata = {
        "upload_id": upload_id,
        "case_id": case_id,
        "evidence_code": evidence_code,
        "file_name": safe_name,
        "mime_type": mime_type,
        "size_bytes": len(content),
        "sha256": digest,
        "stored_name": stored_name,
        "evidence_note": note,
        "content_excerpt": _extract_text(content, mime_type),
    }
    (case_root / f"{upload_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    public_metadata = {
        key: value
        for key, value in metadata.items()
        if key not in {"stored_name", "content_excerpt"}
    }
    public_metadata["inspection"] = evidence_inspection(metadata)
    return public_metadata


def evidence_inspection(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a transparent UI summary of what the zero-dependency server verified."""

    excerpt = str(metadata.get("content_excerpt") or "")
    return {
        "integrity_verified": bool(metadata.get("sha256")),
        "text_extracted": bool(excerpt),
        "excerpt": excerpt[:600],
        "scope": (
            "Readable text and the user note were available to policy analysis."
            if excerpt
            else "Only file metadata and the user note were available; binary contents were not interpreted."
        ),
    }


def load_evidence(
    *, case_id: str, upload_ids: list[str], upload_root: Path = DEFAULT_UPLOAD_ROOT
) -> list[dict[str, Any]]:
    """Resolve uploaded evidence metadata and fail closed on unknown ids."""

    safe_case_id = _safe_token(case_id, fallback="case")
    case_root = upload_root / safe_case_id
    results: list[dict[str, Any]] = []
    for upload_id in upload_ids:
        safe_upload_id = _safe_token(str(upload_id), fallback="")
        if not safe_upload_id or safe_upload_id != upload_id:
            raise ValueError("An evidence upload id is invalid.")
        metadata_path = case_root / f"{safe_upload_id}.json"
        if not metadata_path.is_file():
            raise ValueError(f"Evidence upload not found: {upload_id}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        stored_path = case_root / str(metadata.get("stored_name", ""))
        if metadata.get("case_id") != case_id or not stored_path.is_file():
            raise ValueError(f"Evidence upload is incomplete: {upload_id}")
        results.append(metadata)
    return results


def enrich_case(
    case: dict[str, Any],
    *,
    product_code: str | None,
    uploaded_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply only server-validated user submissions to a copy of the demo case."""

    enriched = deepcopy(case)
    missing = set(str(code) for code in enriched.get("expected_missing_documents", []))
    if product_code:
        product_name = SUPPORTED_PRODUCTS.get(product_code)
        if product_name is None:
            raise ValueError("Select a supported Card or insurance product.")
        enriched["product_code"] = product_code
        enriched["product_name"] = product_name
        enriched["product_resolution_status"] = "resolved"
        missing.discard("exact_card_product")
    for evidence in uploaded_evidence:
        code = str(evidence["evidence_code"])
        field = EVIDENCE_FIELDS.get(code)
        if field is None and not code.startswith(LLM_EVIDENCE_PREFIX):
            raise ValueError(f"Unsupported evidence type: {code}")
        if field is not None:
            enriched[field] = True
            missing.discard(code)
    enriched["expected_missing_documents"] = sorted(missing)
    return enriched


def reanalysis_message(
    case: dict[str, Any], *, uploaded_evidence: list[dict[str, Any]]
) -> str:
    """Build authoritative operational context for a real LLM/RAG reanalysis."""

    document_lines: list[str] = []
    for item in uploaded_evidence:
        line = (
            f"- {item['evidence_code']}: {item['file_name']} "
            f"({item['mime_type']}, sha256 verified)"
        )
        if item.get("evidence_note"):
            line += f"\n  User-supplied document note: {item['evidence_note']}"
        if item.get("content_excerpt"):
            line += f"\n  Server-extracted text: {item['content_excerpt']}"
        else:
            line += "\n  No readable text was extracted; do not infer the document's contents."
        document_lines.append(line)
    documents = "\n".join(document_lines) if document_lines else "- No new file evidence"
    payment = "verified" if case["origin_return_paid_with_card"] else "not verified"
    connected_evidence = "\n".join([
        f"- Flight ticket and itinerary: {_availability(case.get('has_flight_ticket'))}",
        f"- Carrier written confirmation: {_availability(case.get('has_carrier_confirmation'))}",
        f"- Property Irregularity Report: {_availability(case.get('has_pir'))}",
        f"- Itemised expense receipts: {_availability(case.get('has_receipts'))}",
        f"- Policy certificate: {_availability(case.get('has_policy_certificate'))}",
    ])
    return (
        "Reanalyse this travel disruption using the newly submitted, server-validated facts below. "
        "These facts are authoritative and supersede any earlier ambiguity in the synthetic customer wording.\n\n"
        f"Verified product: {case['product_name']} ({case['product_code']})\n"
        f"Traveller relationship: {case['traveler_type']}\n"
        f"Travelling with the Card Member: {'yes' if case['travelling_with_cardmember'] else 'no'}\n"
        f"Travelling party size: {case['family_size']}\n"
        f"Event: {case['event_type']} lasting {case['incident_duration_minutes']} minutes\n"
        f"Route: {case['origin_airport']} to {case['destination_airport']}\n"
        f"Trip duration: {case['trip_duration_days']} days\n"
        f"Round-trip Card payment: {payment}\n"
        f"Expense charged to Card: {'yes' if case['expense_charged_to_card'] else 'no'}\n"
        f"Expense category and amount: {case['expense_category']} · SGD {case['expense_sgd']}\n"
        f"Carrier alternative offered: {'yes' if case['alternative_offered'] else 'no'}\n"
        f"Customer refused the offered alternative: {'yes' if case['alternative_refused'] else 'no'}\n"
        f"Claim notice timing: {case['claim_notice_days']} days\n"
        f"Current connected evidence status:\n{connected_evidence}\n"
        f"Newly uploaded evidence:\n{documents}\n\n"
        "Use public policy evidence to provide the safest current next steps. Do not approve a claim "
        "or promise payment. Identify any information that remains missing."
    )


def _availability(value: Any) -> str:
    return "available and already validated" if bool(value) else "not available"


def _safe_token(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", value)
    return cleaned[:80] or fallback


def _safe_filename(value: str) -> str:
    name = Path(value).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return (cleaned[:100] or "evidence.bin")


def _extract_text(content: bytes, mime_type: str) -> str:
    """Extract text only when the zero-dependency server can do so honestly."""

    if mime_type != "text/plain":
        return ""
    text = content.decode("utf-8", errors="replace")
    normalized = " ".join(text.split())
    return normalized[:4_000]
