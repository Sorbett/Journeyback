#!/usr/bin/env python3
"""Compare lexical retrieval with the configured semantic embedding on a separate holdout."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.benchmarking import (  # noqa: E402
    BM25Ranker,
    evaluate_ranker,
    load_holdout,
    reciprocal_rank_fusion,
)
from journeyback.config import LLMSettings  # noqa: E402
from journeyback.knowledge_base import KnowledgeBase  # noqa: E402
from journeyback.llm_client import JourneybackLLMClient  # noqa: E402
from journeyback.retrieval import SemanticRetriever  # noqa: E402


DEFAULT_HOLDOUT = PROJECT_ROOT / "data" / "evaluation" / "retrieval_holdout.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "retrieval_evaluation"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic", action="store_true", help="Call the configured embedding API for semantic queries.")
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = load_holdout(args.holdout)
    knowledge_base = KnowledgeBase.load()
    bm25 = BM25Ranker(knowledge_base.chunks)
    systems: dict[str, Any] = {
        "bm25": {
            "label": "BM25 lexical baseline",
            "status": "completed",
            **evaluate_ranker(rows, bm25.rank),
        }
    }

    settings = LLMSettings.from_env()
    if args.semantic:
        if not settings.embedding_configured:
            systems["semantic"] = {
                "label": settings.embedding_model,
                "status": "not_run",
                "reason": "The configured embedding API key is unavailable.",
            }
            systems["hybrid"] = {
                "label": f"BM25 + {settings.embedding_model} · RRF",
                "status": "not_run",
                "reason": "The configured embedding API key is unavailable.",
            }
        else:
            client = JourneybackLLMClient(settings)
            retriever = SemanticRetriever(
                client=client,
                embedding_model=settings.embedding_model,
                knowledge_base=knowledge_base,
                hybrid=False,
            )

            semantic_cache: dict[str, list[str]] = {}

            def semantic_rank(query: str, top_k: int) -> list[str]:
                if query not in semantic_cache:
                    semantic_cache[query] = [
                        item["chunk_id"]
                        for item in retriever.retrieve(query, top_k=10)
                    ]
                return semantic_cache[query][:top_k]

            systems["semantic"] = {
                "label": f"{settings.embedding_provider} · {settings.embedding_model}",
                "status": "completed",
                **evaluate_ranker(rows, semantic_rank),
            }
            systems["hybrid"] = {
                "label": f"BM25 + {settings.embedding_model} · RRF",
                "status": "completed",
                **evaluate_ranker(
                    rows,
                    lambda query, top_k: reciprocal_rank_fusion(
                        [bm25.rank(query, top_k=10), semantic_rank(query, 10)],
                        top_k=top_k,
                    ),
                ),
            }
    else:
        systems["semantic"] = {
            "label": settings.embedding_model,
            "status": "not_run",
            "reason": "Run with --semantic to make embedding API calls.",
        }
        systems["hybrid"] = {
            "label": f"BM25 + {settings.embedding_model} · RRF",
            "status": "not_run",
            "reason": "Hybrid fusion requires the semantic ranking; run with --semantic.",
        }

    report = {
        "evaluation_scope": "JourneyBack component-level retrieval holdout",
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "holdout": {
            "path": str(args.holdout.relative_to(PROJECT_ROOT)),
            "sha256": hashlib.sha256(args.holdout.read_bytes()).hexdigest(),
            "queries": len(rows),
            "locales": sorted({row["locale"] for row in rows}),
            "label_source": "manual reading of the public Singapore corpus",
        },
        "systems": systems,
        "limitations": [
            "This evaluates retrieval, not claim eligibility or end-to-end product success.",
            "The labels are author-reviewed and have not been independently adjudicated by a policy expert.",
            "The 600 generated journeys remain a scenario-coverage set and are not used as model-accuracy evidence.",
            "A production benchmark requires a sealed, versioned, double-reviewed test split.",
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "report.html").write_text(_render_html(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _render_html(report: dict[str, Any]) -> str:
    completed = [
        (key, system)
        for key, system in report["systems"].items()
        if system.get("status") == "completed"
    ]
    metric_names = [
        ("hit_rate_at_5", "Hit@5"),
        ("recall_at_5", "Recall@5"),
        ("mrr_at_10", "MRR@10"),
        ("ndcg_at_5", "nDCG@5"),
    ]
    cards = []
    for _, system in completed:
        bars = "".join(
            f'<div class="bar-row"><span>{label}</span><div><i style="width:{system["metrics"][name] * 100:.1f}%"></i></div><strong>{system["metrics"][name] * 100:.1f}%</strong></div>'
            for name, label in metric_names
        )
        cards.append(
            f'<article><p>SYSTEM</p><h2>{html.escape(system["label"])}</h2>{bars}</article>'
        )
    failed_rows = []
    for _, system in completed:
        misses = [item for item in system["results"] if not item["hit_at_5"]]
        failed_rows.append(
            f'<tr><td>{html.escape(system["label"])}</td><td>{len(misses)}</td><td>{", ".join(html.escape(item["query_id"]) for item in misses) or "None"}</td></tr>'
        )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in report["limitations"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JourneyBack retrieval evaluation</title>
<style>
:root{{--navy:#082744;--blue:#006fcf;--ink:#173044;--muted:#667b8c;--line:#d9e2e8;--bg:#f3f6f8}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,sans-serif}}header{{padding:62px max(28px,calc((100% - 1120px)/2));color:white;background:linear-gradient(115deg,#07213a,#075b92)}}header p,article>p{{font-size:10px;font-weight:800;letter-spacing:1.2px}}h1{{max-width:780px;margin:12px 0;font:400 48px Georgia,serif}}header span{{color:#c8dfed;font-size:13px}}main{{width:min(1120px,calc(100% - 40px));margin:30px auto 60px}}.notice{{padding:18px;border-left:4px solid #d08a00;background:#fff6df;font-size:12px;line-height:1.6}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin:22px 0}}article{{padding:24px;border:1px solid var(--line);background:white}}article>p{{color:var(--blue)}}article h2{{margin:8px 0 24px;font:400 24px Georgia,serif}}.bar-row{{display:grid;grid-template-columns:70px 1fr 52px;gap:10px;align-items:center;margin:14px 0;font-size:10px}}.bar-row>div{{height:8px;background:#e7edf1}}.bar-row i{{display:block;height:100%;background:var(--blue)}}.bar-row strong{{text-align:right}}section{{margin-top:24px;padding:24px;border:1px solid var(--line);background:white}}section h2{{font:400 25px Georgia,serif}}table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{padding:11px;border-bottom:1px solid var(--line);text-align:left}}li{{margin:8px 0;color:var(--muted);font-size:11px;line-height:1.5}}@media(max-width:720px){{.grid{{grid-template-columns:1fr}}h1{{font-size:36px}}}}
</style></head><body>
<header><p>JOURNEYBACK · COMPONENT EVALUATION</p><h1>Can the retriever find the right policy evidence?</h1><span>{report["holdout"]["queries"]} independently maintained queries · {", ".join(report["holdout"]["locales"])}</span></header>
<main><div class="notice"><strong>Read this correctly.</strong> This report compares retrieval configurations. It does not measure claim eligibility, customer value or end-to-end agent success.</div>
<div class="grid">{"".join(cards)}</div>
<section><h2>Misses requiring review</h2><table><thead><tr><th>System</th><th>Missed queries</th><th>IDs</th></tr></thead><tbody>{"".join(failed_rows)}</tbody></table></section>
<section><h2>Limitations</h2><ul>{limitations}</ul></section></main></body></html>"""


if __name__ == "__main__":
    main()
