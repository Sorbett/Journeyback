"""Validated synthetic evidence packages for the one-click demo pipeline."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT


PIPELINE_TEST_ROOT = PROJECT_ROOT / "data" / "pipeline_test"
CASE_ID_PATTERN = re.compile(r"JB-SYN-\d{4}")


def pipeline_test_summary(case_id: str) -> dict[str, Any] | None:
    """Return safe display metadata when a generated package exists for a case."""

    try:
        manifest, _ = _load_manifest(case_id)
    except FileNotFoundError:
        return None
    return {
        "case_id": manifest["case_id"],
        "product_code": manifest["product_code"],
        "file_count": len(manifest["files"]),
        "files": [
            {
                "evidence_code": item["evidence_code"],
                "file_name": item["file_name"],
            }
            for item in manifest["files"]
        ],
    }


def pipeline_test_kit(case_id: str) -> dict[str, Any]:
    """Load and integrity-check an API-ready evidence package for one case."""

    try:
        manifest, case_root = _load_manifest(case_id)
    except FileNotFoundError as exc:
        raise ValueError(f"No guided pipeline test kit is available for {case_id}") from exc
    files: list[dict[str, Any]] = []
    for item in manifest["files"]:
        path = case_root / item["file_name"]
        try:
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise OSError(f"Evidence file is missing: {item['file_name']}") from exc
        digest = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(digest, item["sha256"]):
            raise OSError(f"Evidence file failed its integrity check: {item['file_name']}")
        if len(content) != item["size_bytes"]:
            raise OSError(f"Evidence file size does not match its manifest: {item['file_name']}")
        files.append({
            "evidence_code": item["evidence_code"],
            "file_name": item["file_name"],
            "mime_type": item["mime_type"],
            "content_base64": base64.b64encode(content).decode("ascii"),
            "evidence_note": item["evidence_note"],
        })
    return {
        "case_id": manifest["case_id"],
        "product_code": manifest["product_code"],
        "package_mode": manifest["package_mode"],
        "files": files,
    }


def _load_manifest(case_id: str) -> tuple[dict[str, Any], Path]:
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError(f"No guided pipeline test kit is available for {case_id or 'this case'}")
    case_root = PIPELINE_TEST_ROOT / case_id
    manifest_path = case_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No guided pipeline test kit is available for {case_id}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OSError(f"Evidence manifest is invalid for {case_id}") from exc
    if manifest.get("schema_version") != 1 or manifest.get("case_id") != case_id:
        raise OSError(f"Evidence manifest does not match {case_id}")
    if not isinstance(manifest.get("product_code"), str) or not manifest["product_code"]:
        raise OSError(f"Evidence manifest has no product code for {case_id}")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise OSError(f"Evidence manifest has no files for {case_id}")
    seen_codes: set[str] = set()
    for item in raw_files:
        if not isinstance(item, dict):
            raise OSError(f"Evidence manifest has an invalid file entry for {case_id}")
        file_name = item.get("file_name")
        evidence_code = item.get("evidence_code")
        if not isinstance(file_name, str) or Path(file_name).name != file_name:
            raise OSError(f"Evidence manifest contains an unsafe file name for {case_id}")
        if not isinstance(evidence_code, str) or not evidence_code or evidence_code in seen_codes:
            raise OSError(f"Evidence manifest contains an invalid evidence code for {case_id}")
        seen_codes.add(evidence_code)
        if item.get("mime_type") != "text/plain":
            raise OSError(f"Evidence manifest contains an unsupported file type for {case_id}")
        if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise OSError(f"Evidence manifest has an invalid digest for {case_id}")
        if not isinstance(item.get("size_bytes"), int) or item["size_bytes"] <= 0:
            raise OSError(f"Evidence manifest has an invalid file size for {case_id}")
        if not isinstance(item.get("evidence_note"), str):
            raise OSError(f"Evidence manifest has an invalid evidence note for {case_id}")
    return manifest, case_root
