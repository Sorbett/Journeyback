"""Typed loading and filtering for the imported Journeyback knowledge base."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_KB_ROOT = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"


class KnowledgeBaseError(RuntimeError):
    """Raised when the imported knowledge base is missing or invalid."""


@dataclass(frozen=True)
class KnowledgeBase:
    root: Path
    chunks: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    schema: dict[str, Any]
    retrieval_policy: dict[str, Any]
    quality_report: dict[str, Any]

    @classmethod
    def load(cls, root: Path | str = DEFAULT_KB_ROOT) -> "KnowledgeBase":
        root = Path(root).resolve()
        required_files = (
            root / "rag" / "knowledge_base.jsonl",
            root / "rag" / "chunk_schema.json",
            root / "rag" / "retrieval_policy.json",
            root / "normalized" / "sources.json",
            root / "quality_report.json",
            root / "import_manifest.json",
        )
        missing = [str(path) for path in required_files if not path.is_file()]
        if missing:
            raise KnowledgeBaseError(f"Knowledge base is not imported; missing: {', '.join(missing)}")

        chunks = tuple(
            json.loads(line)
            for line in (root / "rag" / "knowledge_base.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        instance = cls(
            root=root,
            chunks=chunks,
            sources=tuple(json.loads((root / "normalized" / "sources.json").read_text(encoding="utf-8"))),
            schema=json.loads((root / "rag" / "chunk_schema.json").read_text(encoding="utf-8")),
            retrieval_policy=json.loads((root / "rag" / "retrieval_policy.json").read_text(encoding="utf-8")),
            quality_report=json.loads((root / "quality_report.json").read_text(encoding="utf-8")),
        )
        instance.validate()
        return instance

    def validate(self) -> None:
        required_fields = set(self.schema.get("required", ()))
        malformed = [chunk.get("chunk_id", "<missing>") for chunk in self.chunks if not required_fields <= set(chunk)]
        if malformed:
            raise KnowledgeBaseError(f"Chunks are missing required fields: {', '.join(malformed[:5])}")

        chunk_ids = [chunk["chunk_id"] for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise KnowledgeBaseError("Duplicate chunk IDs found.")

        source_ids = {source["source_id"] for source in self.sources}
        orphaned = [chunk["chunk_id"] for chunk in self.chunks if chunk["source_id"] not in source_ids]
        if orphaned:
            raise KnowledgeBaseError(f"Chunks reference unknown sources: {', '.join(orphaned[:5])}")

        if any(chunk["synthetic"] for chunk in self.chunks):
            raise KnowledgeBaseError("Runtime knowledge base unexpectedly contains synthetic chunks.")

        expected_chunks = self.quality_report.get("chunk_count")
        if expected_chunks != len(self.chunks):
            raise KnowledgeBaseError(f"Expected {expected_chunks} chunks, loaded {len(self.chunks)}.")

    def filter_chunks(
        self,
        *,
        market: str | None = None,
        product_code: str | None = None,
        document_type: str | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Apply deterministic metadata filters before semantic retrieval."""
        results: list[dict[str, Any]] = []
        for chunk in self.chunks:
            if market is not None and chunk["market"] != market:
                continue
            if product_code is not None and chunk["product_code"] != product_code:
                continue
            if document_type is not None and chunk["document_type"] != document_type:
                continue
            if topic is not None and topic not in chunk["topics"]:
                continue
            results.append(chunk)
        return results

    def summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "sources": len(self.sources),
            "chunks": len(self.chunks),
            "formal_policy_chunks": sum(
                chunk["document_type"] == "formal_policy_wording" for chunk in self.chunks
            ),
            "quality_checks_passed": self.quality_report.get("all_checks_passed", False),
        }

