"""Embedding-based semantic retrieval over the Journeyback knowledge base."""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from pathlib import Path
from typing import Any

from .benchmarking import BM25Ranker, reciprocal_rank_fusion
from .config import PROJECT_ROOT
from .knowledge_base import KnowledgeBase
from .llm_client import LLMClient


DEFAULT_CACHE_ROOT = PROJECT_ROOT / ".journeyback_cache"


class SemanticRetriever:
    """Rank policy chunks with BGE-M3 and generic BM25 reciprocal-rank fusion.

    Product, event and payment facts are encoded in the query and chunk text.
    There is no event threshold table or hand-authored policy score in the
    runtime path. Embeddings are cached by model and content hash; lexical and
    semantic ranks are fused without product-specific weights.
    """

    def __init__(
        self,
        *,
        client: LLMClient,
        embedding_model: str,
        knowledge_base: KnowledgeBase | None = None,
        cache_path: Path | None | bool = None,
        hybrid: bool = True,
    ) -> None:
        self.client = client
        self.embedding_model = embedding_model
        self.knowledge_base = knowledge_base or KnowledgeBase.load()
        self.by_chunk_id = {chunk["chunk_id"]: chunk for chunk in self.knowledge_base.chunks}
        self.hybrid = hybrid
        self.lexical_ranker = BM25Ranker(self.knowledge_base.chunks) if hybrid else None
        self._memory_vectors: dict[str, list[float]] | None = None
        self._cache_lock = threading.Lock()
        if cache_path is False:
            self.cache_path: Path | None = None
        elif isinstance(cache_path, Path):
            self.cache_path = cache_path
        else:
            slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", embedding_model)
            self.cache_path = DEFAULT_CACHE_ROOT / f"embeddings_{slug}.json"

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        product_code: str | None = None,
    ) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            raise ValueError("Semantic retrieval query cannot be empty.")
        candidates = [
            chunk
            for chunk in self.knowledge_base.chunks
            if product_code is None or chunk["product_code"] == product_code
        ]
        if not candidates:
            raise ValueError(f"No policy chunks exist for product: {product_code}")
        candidate_ids = {chunk["chunk_id"] for chunk in candidates}
        corpus_vectors = self._corpus_vectors()
        query_vector = self.client.embed([query])[0]
        ranked = [
            (_cosine_similarity(query_vector, corpus_vectors[chunk["chunk_id"]]), chunk)
            for chunk in candidates
        ]
        ranked.sort(key=lambda item: (item[0], float(item[1]["authority_score"])), reverse=True)
        if not self.hybrid:
            return [self._public_result(chunk, score, "semantic") for score, chunk in ranked[:top_k]]

        semantic_ids = [chunk["chunk_id"] for _, chunk in ranked]
        assert self.lexical_ranker is not None
        lexical_ids = [
            chunk_id
            for chunk_id in self.lexical_ranker.rank(
                query, top_k=len(self.knowledge_base.chunks)
            )
            if chunk_id in candidate_ids
        ]
        fused_ids = reciprocal_rank_fusion(
            [semantic_ids, lexical_ids], top_k=top_k
        )
        similarity_by_id = {chunk["chunk_id"]: score for score, chunk in ranked}
        return [
            self._public_result(
                self.by_chunk_id[chunk_id], similarity_by_id[chunk_id], "hybrid_rrf"
            )
            for chunk_id in fused_ids
        ]

    def cache_summary(self) -> dict[str, Any]:
        """Expose safe cache state for diagnostics without loading or rebuilding vectors."""

        cache_present = bool(self.cache_path and self.cache_path.is_file())
        cache_bytes = self.cache_path.stat().st_size if cache_present and self.cache_path else 0
        return {
            "persistent": self.cache_path is not None,
            "cache_present": cache_present,
            "cache_bytes": cache_bytes,
            "corpus_loaded_in_memory": self._memory_vectors is not None,
            "rebuild_policy": "only_missing_or_changed_chunks",
            "retrieval_strategy": "bm25_bge_m3_rrf" if self.hybrid else "semantic_only",
        }

    def _corpus_vectors(self) -> dict[str, list[float]]:
        if self._memory_vectors is not None:
            return self._memory_vectors
        with self._cache_lock:
            if self._memory_vectors is not None:
                return self._memory_vectors
            cached = self._read_cache()
            vectors: dict[str, list[float]] = {}
            missing: list[dict[str, Any]] = []
            for chunk in self.knowledge_base.chunks:
                record = cached.get(chunk["chunk_id"])
                content_hash = _content_hash(chunk)
                if record and record.get("content_hash") == content_hash and isinstance(record.get("embedding"), list):
                    vectors[chunk["chunk_id"]] = record["embedding"]
                else:
                    missing.append(chunk)

            for start in range(0, len(missing), 64):
                batch = missing[start : start + 64]
                embeddings = self.client.embed([_embedding_text(chunk) for chunk in batch])
                if len(embeddings) != len(batch):
                    raise ValueError("Embedding provider returned an incomplete corpus batch.")
                for chunk, embedding in zip(batch, embeddings):
                    vectors[chunk["chunk_id"]] = embedding

            if missing and self.cache_path is not None:
                self._write_cache(vectors)
            self._memory_vectors = vectors
            return vectors

    def _read_cache(self) -> dict[str, dict[str, Any]]:
        if self.cache_path is None or not self.cache_path.is_file():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if payload.get("embedding_model") != self.embedding_model:
            return {}
        records = payload.get("records")
        return records if isinstance(records, dict) else {}

    def _write_cache(self, vectors: dict[str, list[float]]) -> None:
        assert self.cache_path is not None
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        records = {
            chunk["chunk_id"]: {
                "content_hash": _content_hash(chunk),
                "embedding": vectors[chunk["chunk_id"]],
            }
            for chunk in self.knowledge_base.chunks
        }
        payload = {
            "version": 1,
            "embedding_model": self.embedding_model,
            "chunk_count": len(records),
            "records": records,
        }
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.cache_path)

    @staticmethod
    def _public_result(
        chunk: dict[str, Any], similarity: float, retrieval_method: str
    ) -> dict[str, Any]:
        return {
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "market": chunk["market"],
            "product": chunk["product"],
            "product_code": chunk["product_code"],
            "document_type": chunk["document_type"],
            "authority_score": chunk["authority_score"],
            "topics": chunk["topics"],
            "section": chunk["section"],
            "pages": chunk["pages"],
            "citation": chunk["citation"],
            "url": chunk["url"],
            "excerpt": chunk["retrieval_text"][:700],
            "similarity": round(similarity, 6),
            "retrieval_method": retrieval_method,
        }


def _embedding_text(chunk: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Market: {chunk['market']}",
            f"Product: {chunk['product']} ({chunk['product_code']})",
            f"Document type: {chunk['document_type']}",
            f"Section: {chunk['section']}",
            f"Topics: {', '.join(chunk['topics'])}",
            chunk["retrieval_text"],
        ]
    )


def _content_hash(chunk: dict[str, Any]) -> str:
    existing = chunk.get("content_hash")
    if isinstance(existing, str) and existing:
        return existing
    return hashlib.sha256(_embedding_text(chunk).encode("utf-8")).hexdigest()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding dimensions do not match.")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
