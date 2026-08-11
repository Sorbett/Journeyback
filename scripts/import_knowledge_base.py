#!/usr/bin/env python3
"""Import the approved Journeyback RAG knowledge base into the project."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = PROJECT_ROOT / "data" / "knowledge_base"

RUNTIME_FILES = (
    Path("rag/knowledge_base.jsonl"),
    Path("rag/chunk_schema.json"),
    Path("rag/retrieval_policy.json"),
    Path("rag/retrieval_qa.json"),
    Path("rag/source_manifest.csv"),
    Path("normalized/policy_facts.json"),
    Path("normalized/sources.json"),
    Path("quality_report.json"),
    Path("README.md"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory containing rag/, normalized/ and quality_report.json.",
    )
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()

    missing = [str(relative) for relative in RUNTIME_FILES if not (source / relative).is_file()]
    if missing:
        raise SystemExit(f"Knowledge-base source is incomplete; missing: {', '.join(missing)}")

    quality_report = json.loads((source / "quality_report.json").read_text(encoding="utf-8"))
    if not quality_report.get("all_checks_passed"):
        raise SystemExit("Refusing to import a knowledge base that failed its quality checks.")

    imported_files: list[dict[str, object]] = []
    for relative in RUNTIME_FILES:
        source_file = source / relative
        destination_file = destination / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)

        source_hash = sha256_file(source_file)
        destination_hash = sha256_file(destination_file)
        if source_hash != destination_hash:
            raise SystemExit(f"Hash mismatch after importing {relative}")
        imported_files.append(
            {
                "path": relative.as_posix(),
                "bytes": destination_file.stat().st_size,
                "sha256": destination_hash,
            }
        )

    manifest = {
        "schema_version": "1.0",
        "source": "JourneyBack Benefits RAG Knowledge Base v1",
        "source_root": str(source),
        "source_generated_at": quality_report.get("generated_at"),
        "source_count": quality_report.get("source_count"),
        "chunk_count": quality_report.get("chunk_count"),
        "quality_checks_passed": True,
        "files": imported_files,
    }
    manifest_path = destination / "import_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"Imported {len(imported_files)} files, "
        f"{manifest['source_count']} sources and {manifest['chunk_count']} chunks "
        f"into {destination}"
    )


if __name__ == "__main__":
    main()
