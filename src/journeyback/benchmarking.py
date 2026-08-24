"""Small reproducible retrieval benchmark utilities with no third-party dependencies."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable


Ranker = Callable[[str, int], list[str]]


def load_holdout(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    for row in rows:
        query_id = str(row.get("query_id", ""))
        expected = row.get("expected_chunk_ids")
        if not query_id or query_id in seen or not isinstance(expected, list) or not expected:
            raise ValueError("The retrieval holdout contains an invalid row.")
        seen.add(query_id)
    return rows


class BM25Ranker:
    """Lexical baseline over the exact corpus used by the semantic retriever."""

    def __init__(self, chunks: list[dict[str, Any]], *, k1: float = 1.5, b: float = 0.75) -> None:
        if not chunks:
            raise ValueError("BM25 requires at least one corpus chunk.")
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.documents = [_tokens(_document_text(chunk)) for chunk in chunks]
        self.term_frequencies = [Counter(document) for document in self.documents]
        self.average_length = sum(len(document) for document in self.documents) / len(self.documents)
        self.document_frequency: Counter[str] = Counter()
        for document in self.documents:
            self.document_frequency.update(set(document))

    def rank(self, query: str, top_k: int = 10) -> list[str]:
        terms = _tokens(query)
        total = len(self.documents)
        scored: list[tuple[float, float, str]] = []
        for chunk, document, frequencies in zip(
            self.chunks, self.documents, self.term_frequencies
        ):
            score = 0.0
            length_ratio = len(document) / self.average_length if self.average_length else 1.0
            for term in terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                document_frequency = self.document_frequency[term]
                inverse_frequency = math.log(
                    1 + (total - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length_ratio
                )
                score += inverse_frequency * frequency * (self.k1 + 1) / denominator
            scored.append(
                (score, float(chunk.get("authority_score", 0)), str(chunk["chunk_id"]))
            )
        scored.sort(reverse=True)
        return [chunk_id for _, _, chunk_id in scored[:top_k]]


def evaluate_ranker(rows: list[dict[str, Any]], ranker: Ranker) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for row in rows:
        ranked = ranker(str(row["query"]), 10)
        expected = [str(value) for value in row["expected_chunk_ids"]]
        expected_set = set(expected)
        relevant_ranks = [
            index + 1 for index, chunk_id in enumerate(ranked) if chunk_id in expected_set
        ]
        top_five = ranked[:5]
        hits_at_five = expected_set.intersection(top_five)
        reciprocal_rank = 1 / relevant_ranks[0] if relevant_ranks else 0.0
        dcg = sum(
            1 / math.log2(index + 2)
            for index, chunk_id in enumerate(top_five)
            if chunk_id in expected_set
        )
        ideal_hits = min(5, len(expected_set))
        ideal_dcg = sum(1 / math.log2(index + 2) for index in range(ideal_hits))
        results.append({
            "query_id": row["query_id"],
            "locale": row.get("locale", ""),
            "category": row.get("category", ""),
            "query": row["query"],
            "expected_chunk_ids": expected,
            "top_10_chunk_ids": ranked,
            "first_relevant_rank": relevant_ranks[0] if relevant_ranks else None,
            "hit_at_5": bool(hits_at_five),
            "recall_at_5": len(hits_at_five) / len(expected_set),
            "reciprocal_rank": reciprocal_rank,
            "ndcg_at_5": dcg / ideal_dcg if ideal_dcg else 0.0,
        })
    total = len(results)
    return {
        "query_count": total,
        "metrics": {
            "hit_rate_at_5": _average([float(item["hit_at_5"]) for item in results]),
            "recall_at_5": _average([item["recall_at_5"] for item in results]),
            "mrr_at_10": _average([item["reciprocal_rank"] for item in results]),
            "ndcg_at_5": _average([item["ndcg_at_5"] for item in results]),
        },
        "locale_breakdown": {
            locale: _locale_metrics(results, locale)
            for locale in sorted({str(item["locale"]) for item in results})
        },
        "results": results,
    }


def reciprocal_rank_fusion(
    rankings: list[list[str]], *, top_k: int = 10, constant: int = 60
) -> list[str]:
    """Fuse lexical and semantic rankings without introducing tuned policy rules."""

    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        for index, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (constant + index)
            best_rank[chunk_id] = min(index, best_rank.get(chunk_id, index))
    ordered = sorted(
        scores,
        key=lambda chunk_id: (scores[chunk_id], -best_rank[chunk_id], chunk_id),
        reverse=True,
    )
    return ordered[:top_k]


def _locale_metrics(results: list[dict[str, Any]], locale: str) -> dict[str, float | int]:
    selected = [item for item in results if item["locale"] == locale]
    return {
        "queries": len(selected),
        "hit_rate_at_5": _average([float(item["hit_at_5"]) for item in selected]),
        "mrr_at_10": _average([item["reciprocal_rank"] for item in selected]),
    }


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _document_text(chunk: dict[str, Any]) -> str:
    return "\n".join([
        str(chunk.get("product", "")),
        str(chunk.get("product_code", "")),
        str(chunk.get("section", "")),
        " ".join(str(value) for value in chunk.get("topics", [])),
        str(chunk.get("retrieval_text", "")),
    ])


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    latin = re.findall(r"[a-z0-9]+", normalized)
    cjk_blocks = re.findall(r"[\u3400-\u9fff]+", normalized)
    cjk: list[str] = []
    for block in cjk_blocks:
        cjk.extend(block)
        cjk.extend(block[index : index + 2] for index in range(len(block) - 1))
    return latin + cjk
