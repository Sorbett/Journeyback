"""Generate persisted, reviewable recovery artifacts for the product demo."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence_store import DEFAULT_UPLOAD_ROOT


ACTION_CODES = {"prepare_carrier_request", "build_evidence_pack"}


def save_reanalysis_snapshot(
    *,
    case_id: str,
    product_code: str | None,
    evidence_upload_ids: list[str],
    recovery: dict[str, Any],
    artifact_root: Path = DEFAULT_UPLOAD_ROOT,
) -> None:
    """Persist the live result used by the next server-backed recovery action."""

    safe_case_id = _safe_token(case_id, fallback="")
    if safe_case_id != case_id or recovery.get("case_id") != case_id:
        raise ValueError("The live reanalysis snapshot is invalid.")
    normalized_ids = sorted(set(str(value) for value in evidence_upload_ids))
    case_root = artifact_root / safe_case_id
    case_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case_id,
        "product_code": product_code,
        "evidence_upload_ids": normalized_ids,
        "recovery": recovery,
    }
    path = case_root / _snapshot_filename(
        case_id=case_id,
        product_code=product_code,
        evidence_upload_ids=normalized_ids,
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_reanalysis_snapshot(
    *,
    case_id: str,
    product_code: str | None,
    evidence_upload_ids: list[str],
    artifact_root: Path = DEFAULT_UPLOAD_ROOT,
) -> dict[str, Any] | None:
    """Load the exact live result for a matching product and evidence set."""

    safe_case_id = _safe_token(case_id, fallback="")
    if safe_case_id != case_id:
        raise ValueError("The case identifier is invalid.")
    normalized_ids = sorted(set(str(value) for value in evidence_upload_ids))
    path = artifact_root / safe_case_id / _snapshot_filename(
        case_id=case_id,
        product_code=product_code,
        evidence_upload_ids=normalized_ids,
    )
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("case_id") != case_id
        or payload.get("product_code") != product_code
        or payload.get("evidence_upload_ids") != normalized_ids
        or not isinstance(payload.get("recovery"), dict)
        or payload["recovery"].get("case_id") != case_id
    ):
        raise ValueError("The stored live reanalysis snapshot is invalid.")
    return payload["recovery"]


def create_recovery_artifact(
    *,
    case: dict[str, Any],
    action_code: str,
    recovery: dict[str, Any],
    uploaded_evidence: list[dict[str, Any]],
    artifact_root: Path = DEFAULT_UPLOAD_ROOT,
) -> dict[str, Any]:
    """Create a local draft or review pack instead of toggling a cosmetic checkbox."""

    if action_code not in ACTION_CODES:
        raise ValueError("This recovery action is not supported.")
    artifact_id = f"ART-{secrets.token_hex(8)}"
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    case_root = artifact_root / _safe_token(str(case["case_id"]), fallback="case")
    case_root.mkdir(parents=True, exist_ok=True)

    if action_code == "prepare_carrier_request":
        filename = f"{artifact_id}_carrier-request.txt"
        title = "Carrier confirmation request"
        payload = _carrier_request(case, recovery, created_at=created_at)
        body = f"Subject: {payload['subject']}\n\n{payload['body']}\n"
        media_type = "text/plain"
        preview = {
            "type": "message_draft",
            "title": title,
            "subject": payload["subject"],
            "body": payload["body"],
        }
    else:
        filename = f"{artifact_id}_review-pack.json"
        title = "JourneyBack review pack"
        payload = _review_pack(
            case,
            recovery,
            uploaded_evidence=uploaded_evidence,
            created_at=created_at,
        )
        body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        media_type = "application/json"
        preview = {
            "type": "review_pack",
            "title": title,
            "facts": 5,
            "evidence_items": len(payload["submitted_evidence"]),
            "policy_sources": len(payload["policy_evidence"]),
            "remaining_items": len(payload["remaining_information"]),
        }

    artifact_path = case_root / filename
    artifact_path.write_text(body, encoding="utf-8")
    metadata = {
        "artifact_id": artifact_id,
        "case_id": case["case_id"],
        "action_code": action_code,
        "title": title,
        "file_name": filename,
        "media_type": media_type,
        "created_at": created_at,
    }
    (case_root / f"{artifact_id}.artifact.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **metadata,
        "status": "created",
        "preview": preview,
        "download_path": f"/api/artifact?case_id={case['case_id']}&artifact_id={artifact_id}",
    }


def load_recovery_artifact(
    *, case_id: str, artifact_id: str, artifact_root: Path = DEFAULT_UPLOAD_ROOT
) -> tuple[dict[str, Any], bytes]:
    """Load one persisted artifact after validating both identifiers and metadata."""

    safe_case_id = _safe_token(case_id, fallback="")
    safe_artifact_id = _safe_token(artifact_id, fallback="")
    if safe_case_id != case_id or safe_artifact_id != artifact_id:
        raise ValueError("The artifact identifier is invalid.")
    case_root = artifact_root / safe_case_id
    metadata_path = case_root / f"{safe_artifact_id}.artifact.json"
    if not metadata_path.is_file():
        raise ValueError("The recovery artifact was not found.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("case_id") != case_id or metadata.get("artifact_id") != artifact_id:
        raise ValueError("The recovery artifact metadata is invalid.")
    artifact_path = case_root / Path(str(metadata.get("file_name", ""))).name
    if not artifact_path.is_file():
        raise ValueError("The recovery artifact is incomplete.")
    return metadata, artifact_path.read_bytes()


def _carrier_request(
    case: dict[str, Any], recovery: dict[str, Any], *, created_at: str
) -> dict[str, str]:
    trip = recovery["trip"]
    flight = next(segment for segment in trip["segments"] if segment["type"] == "flight")
    disruption = recovery["disruption"]
    subject = f"Written disruption confirmation request · {flight['service_number']}"
    body = (
        "Hello,\n\n"
        f"Please provide written confirmation for the disruption affecting {flight['service_number']} "
        f"from {flight['origin_code']} to {flight['destination_code']} on "
        f"{flight['departure_local']}. The recorded event is {disruption['headline'].lower()} "
        f"with a duration of {disruption['duration']}.\n\n"
        "Please confirm:\n"
        "• the operational reason and time the disruption began;\n"
        "• the actual or revised departure time;\n"
        "• the earliest alternative offered; and\n"
        "• any meals, accommodation, transport or refund offered.\n\n"
        f"Reference: {disruption['carrier_reference']} / {case['case_id']}\n"
        f"Draft generated: {created_at}\n\n"
        "Thank you."
    )
    return {"subject": subject, "body": body}


def _review_pack(
    case: dict[str, Any],
    recovery: dict[str, Any],
    *,
    uploaded_evidence: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    benefit = recovery["benefit_match"]
    return {
        "schema_version": "1.0",
        "artifact_type": "journeyback_human_review_pack",
        "status": "draft_for_formal_review",
        "created_at": created_at,
        "case_id": case["case_id"],
        "synthetic_demo": True,
        "journey": {
            "route": recovery["trip"]["route"],
            "dates": recovery["trip"]["date_range"],
            "event": recovery["disruption"]["headline"],
            "duration": recovery["disruption"]["duration"],
        },
        "protection": {
            "product_code": case["product_code"],
            "product_name": case["product_name"],
            "round_trip_payment_verified": bool(case["origin_return_paid_with_card"]),
        },
        "guidance": {
            "status": benefit["status"],
            "headline": benefit["headline"],
            "summary": benefit["summary"],
            "human_review_required": True,
        },
        "policy_evidence": [
            {
                "chunk_id": item["chunk_id"],
                "section": item["section"],
                "citation": item.get("citation", ""),
                "url": item["url"],
            }
            for item in benefit.get("policy_evidence", [])
        ],
        "submitted_evidence": [
            {
                "upload_id": item["upload_id"],
                "evidence_code": item["evidence_code"],
                "file_name": item["file_name"],
                "mime_type": item["mime_type"],
                "sha256": item["sha256"],
                "note": item.get("evidence_note", ""),
                "text_extracted": bool(item.get("content_excerpt")),
            }
            for item in uploaded_evidence
        ],
        "remaining_information": list(recovery.get("missing_information", [])),
        "recommended_actions": recovery.get("recovery_actions", []),
        "safety_note": recovery["safety_note"],
    }


def _safe_token(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", value)
    return cleaned[:80] or fallback


def _snapshot_filename(
    *, case_id: str, product_code: str | None, evidence_upload_ids: list[str]
) -> str:
    identity = json.dumps(
        {
            "case_id": case_id,
            "product_code": product_code,
            "evidence_upload_ids": evidence_upload_ids,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:20]
    return f"REANALYSIS-{digest}.json"
