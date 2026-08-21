#!/usr/bin/env python3
"""Run all synthetic cases and build a standalone visual product-need report."""

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

from journeyback.synthetic_demo import dataset_insights, synthetic_cases  # noqa: E402


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "synthetic_evaluation"

OUTCOME_LABELS = {
    "potentially_eligible": "Potential match",
    "unlikely_eligible": "Condition not met",
    "insufficient_information": "More information needed",
    "manual_review_required": "Manual policy review",
    "out_of_scope": "Product handoff",
}

EVENT_LABELS = {
    "missed_connection": "Missed connection",
    "flight_delay": "Flight delay",
    "baggage_delay": "Baggage delay",
    "baggage_loss": "Baggage loss",
    "flight_cancellation": "Flight cancellation",
    "card_loss": "Card loss",
    "hotel_issue": "Hotel issue",
}

INTERVENTIONS = {
    "policy_explanation_with_human_review": "Explain potential benefit and prepare evidence",
    "ineligible_explanation_with_human_review": "Explain the limiting condition and offer a safe next step",
    "request_more_information": "Prompt for missing evidence before the case stalls",
    "manual_policy_review": "Preserve time-sensitive facts and route to a specialist",
    "out_of_scope_handoff": "Resolve the exact Card product through an authorised channel",
}


def evaluate_cases(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Materialise one deterministic expected result per generated case."""

    cases = synthetic_cases()
    insights = dataset_insights()
    source_bytes = (PROJECT_ROOT / "data" / "synthetic" / "journeyback_cases.jsonl").read_bytes()
    results = [
        {
            "case_id": case["case_id"],
            "split": case["split"],
            "language": case["language"],
            "product_name": case["product_name"],
            "event_type": case["event_type"],
            "scenario_class": case["scenario_class"],
            "expected_eligibility": case["expected_eligibility"],
            "expected_routing": case["expected_routing"],
            "journeyback_intervention": INTERVENTIONS[case["expected_routing"]],
            "missing_document_count": len(case["expected_missing_documents"]),
            "expected_action_count": len(case["expected_actions"]),
            "policy_evidence_count": len(case["expected_chunk_ids"]),
            "human_review_required": case["human_review_required"] is True,
            "payout_prediction_suppressed": case["expected_payout_sgd"] is None,
            "result_status": "expected_result_materialised",
        }
        for case in cases
    ]

    total = len(results)
    summary: dict[str, Any] = {
        "evaluation_scope": "JourneyBack synthetic product-need evaluation",
        "status": "completed",
        "evaluation_mode": "deterministic_expected_outcomes",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "dataset_size": total,
        "materialised_results": len(results),
        "metrics": {
            **insights["headline_metrics"],
            "human_review_guardrail": _rate(sum(row["human_review_required"] for row in results), total),
            "payout_prediction_suppressed": _rate(sum(row["payout_prediction_suppressed"] for row in results), total),
            "cases_with_policy_evidence": _rate(sum(row["policy_evidence_count"] > 0 for row in results), total),
            "average_recommended_actions": round(
                sum(row["expected_action_count"] for row in results) / total, 2
            ),
        },
        "outcomes": insights["outcomes"],
        "events": insights["events"],
        "products": insights["products"],
        "product_need": insights["product_need"],
        "limitations": [
            "All journeys and expected results are synthetic; this report does not measure real claim incidence.",
            "This deterministic run validates coverage, routing and product-need scenarios, not live LLM accuracy.",
            "Run scripts/evaluate_mvp.py separately for a small live model and citation smoke test.",
            "Final benefit applicability and claims always require formal review.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.html").write_text(_report_html(summary), encoding="utf-8")
    return summary


def _report_html(summary: dict[str, Any]) -> str:
    total = int(summary["dataset_size"])
    metrics = summary["metrics"]
    outcome_chart = _bar_chart(summary["outcomes"], OUTCOME_LABELS, total, "outcome")
    event_chart = _bar_chart(summary["events"], EVENT_LABELS, total, "event")
    product_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{count}</td><td>{_percent(count, total):.1f}%</td></tr>"
        for name, count in summary["products"].items()
    )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in summary["limitations"])
    generated_at = html.escape(str(summary["generated_at"]))
    dataset_hash = html.escape(str(summary["dataset_sha256"])[:12])
    triage = metrics["needs_explanation_or_triage"]
    documents = metrics["missing_key_documents"]
    non_english = metrics["non_english_cases"]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JourneyBack synthetic evaluation</title>
  <style>
    :root {{ --navy:#0a2747; --deep:#071d34; --blue:#006fcf; --sky:#67b8e8; --ink:#172b3d; --muted:#607386; --line:#d8e2e9; --bg:#f4f7f9; --white:#fff; --amber:#d28a00; font-family:Inter,"Helvetica Neue",Arial,sans-serif; color:var(--ink); background:var(--bg); }}
    * {{ box-sizing:border-box; }} body {{ margin:0; }}
    header {{ padding:30px max(24px,calc((100% - 1160px)/2)); color:white; background:linear-gradient(115deg,var(--deep),#0b568b); }}
    .brand {{ display:flex; align-items:center; gap:10px; margin-bottom:62px; font-size:17px; font-weight:700; }}
    .brand i {{ display:block; width:28px; height:16px; border:2px solid #84d0f7; border-left:0; border-radius:0 20px 20px 0; }}
    header p {{ max-width:720px; color:#c8dbea; font-size:12px; line-height:1.6; }}
    h1 {{ max-width:760px; margin:0; font-family:Georgia,serif; font-size:clamp(34px,5vw,57px); font-weight:400; line-height:1.03; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:25px; color:#9dc3dd; font-size:9px; text-transform:uppercase; letter-spacing:.08em; }}
    main {{ width:min(1160px,calc(100% - 48px)); margin:0 auto; padding:46px 0 70px; }}
    .method {{ padding:17px 20px; border-left:4px solid var(--blue); background:#e9f4fb; color:#31536d; font-size:11px; line-height:1.55; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px; margin:34px 0 54px; background:var(--line); }}
    .metric {{ min-height:175px; padding:29px; background:white; }} .metric strong {{ display:block; color:var(--navy); font-family:Georgia,serif; font-size:46px; font-weight:400; }}
    .metric span {{ display:block; margin:7px 0; font-size:11px; font-weight:700; }} .metric small {{ color:var(--muted); font-size:9px; line-height:1.5; }}
    .section-head {{ display:grid; grid-template-columns:1fr 1fr; gap:60px; align-items:end; margin-bottom:25px; }}
    h2 {{ margin:0; color:var(--navy); font-family:Georgia,serif; font-size:30px; font-weight:400; }} .section-head p {{ margin:0; color:var(--muted); font-size:11px; line-height:1.6; }}
    .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:60px; margin-bottom:60px; }} h3 {{ margin:0 0 21px; color:var(--navy); font-size:12px; }}
    .chart {{ display:grid; gap:13px; }} .bar-row {{ display:grid; grid-template-columns:135px 1fr 58px; gap:10px; align-items:center; }}
    .bar-row>span {{ color:var(--muted); font-size:9px; }} .track {{ height:12px; background:#e7edf2; }} .track i {{ display:block; height:100%; background:var(--blue); }}
    .event .track i {{ background:#78afd1; }} .bar-row strong {{ color:var(--navy); font-size:9px; }} .bar-row small {{ color:var(--muted); font-weight:400; }}
    .interventions {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:0 0 60px; padding:0; list-style:none; counter-reset:step; }}
    .interventions li {{ min-height:164px; padding:20px 16px; border-top:3px solid var(--blue); background:white; font-size:10px; line-height:1.5; counter-increment:step; }}
    .interventions li::before {{ display:block; margin-bottom:25px; color:var(--blue); content:"0" counter(step); font-family:Georgia,serif; font-size:21px; }}
    .detail-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:40px; }} table {{ width:100%; border-collapse:collapse; background:white; font-size:10px; }}
    th,td {{ padding:12px 14px; border-bottom:1px solid var(--line); text-align:left; }} th {{ color:var(--muted); font-size:8px; text-transform:uppercase; }}
    .guardrails {{ padding:25px 28px; color:white; background:var(--navy); }} .guardrails h3 {{ color:white; }} .guardrails strong {{ display:block; margin-bottom:8px; font-family:Georgia,serif; font-size:31px; font-weight:400; }}
    .guardrails span {{ color:#bdd1e1; font-size:9px; }} .guardrails ul {{ margin:24px 0 0; padding-left:18px; color:#dce8f1; font-size:9px; line-height:1.8; }}
    footer {{ padding:24px max(24px,calc((100% - 1160px)/2)); color:#728392; background:white; font-size:8px; }}
    @media(max-width:780px) {{ .metrics,.charts,.detail-grid,.section-head {{ grid-template-columns:1fr; }} .interventions {{ grid-template-columns:1fr 1fr; }} .section-head {{ gap:12px; }} }}
    @media(max-width:480px) {{ main {{ width:calc(100% - 28px); }} .interventions {{ grid-template-columns:1fr; }} .bar-row {{ grid-template-columns:108px 1fr 50px; }} }}
  </style>
</head>
<body>
  <header>
    <div class="brand"><i aria-hidden="true"></i>JourneyBack</div>
    <h1>What 600 synthetic journeys tell us about travel recovery</h1>
    <p>A deterministic evaluation of where travellers need policy explanation, evidence prompts and safe human routing after disruption. It explains the product need; it does not estimate real claim incidence.</p>
    <div class="meta"><span>Completed · {total} / {total} results</span><span>Dataset {dataset_hash}</span><span>{generated_at}</span></div>
  </header>
  <main>
    <div class="method"><strong>How to read this report.</strong> Every result below is materialised from the benchmark’s rule-authored expected routing and safety labels. No API key, live model call or payout prediction is used.</div>
    <section class="metrics" aria-label="Headline metrics">
      <article class="metric"><strong>{triage['percent']}%</strong><span>need explanation or triage</span><small>{triage['count']} journeys are not a straightforward potential match. Customers still need a useful, safe next step.</small></article>
      <article class="metric"><strong>{documents['percent']}%</strong><span>have a key evidence gap</span><small>{documents['count']} journeys can benefit from proactive document prompts before formal review begins.</small></article>
      <article class="metric"><strong>{non_english['percent']}%</strong><span>are non-English scenarios</span><small>{non_english['count']} journeys demonstrate the need for multilingual, consistent policy navigation.</small></article>
    </section>

    <section>
      <div class="section-head"><h2>One disruption, five different customer outcomes</h2><p>{html.escape(summary['product_need'])} The right product experience is guidance and orchestration, not an automated claim decision.</p></div>
      <div class="charts">
        <div><h3>Expected outcome · share of all journeys</h3>{outcome_chart}</div>
        <div><h3>Disruption mix · share of all journeys</h3>{event_chart}</div>
      </div>
    </section>

    <section>
      <div class="section-head"><h2>Where JourneyBack creates value</h2><p>Each benchmark routing maps to a distinct intervention. A single claim form cannot handle this range well.</p></div>
      <ol class="interventions">
        <li>Explain a potential benefit and assemble the evidence path.</li>
        <li>Explain why a condition may not be met without abandoning the traveller.</li>
        <li>Ask for the missing document while the carrier interaction is still fresh.</li>
        <li>Recognise a timing or wording boundary and escalate safely.</li>
        <li>Resolve an unknown product before presenting benefit-specific guidance.</li>
      </ol>
    </section>

    <section class="detail-grid">
      <div><h3>Coverage across Card and insurance products</h3><table><thead><tr><th>Product</th><th>Cases</th><th>Share</th></tr></thead><tbody>{product_rows}</tbody></table></div>
      <div class="guardrails"><h3>Safety contract validated on every row</h3><strong>{metrics['human_review_guardrail']['percent']}% human review</strong><span>{metrics['payout_prediction_suppressed']['percent']}% suppress payout prediction · {metrics['cases_with_policy_evidence']['percent']}% include expected public-policy evidence</span><ul>{limitations}</ul></div>
    </section>
  </main>
  <footer>JourneyBack synthetic evaluation · Generated by scripts/evaluate_synthetic_cases.py · Re-run after any dataset change.</footer>
</body>
</html>
"""


def _bar_chart(
    counts: dict[str, int], labels: dict[str, str], total: int, class_name: str
) -> str:
    maximum = max(counts.values())
    rows = "".join(
        (
            f'<div class="bar-row"><span>{html.escape(labels.get(key, key))}</span>'
            f'<div class="track"><i style="width:{100 * count / maximum:.1f}%"></i></div>'
            f'<strong>{count} <small>{_percent(count, total):.1f}%</small></strong></div>'
        )
        for key, count in counts.items()
    )
    accessible = "; ".join(f"{labels.get(key, key)} {count}" for key, count in counts.items())
    return f'<div class="chart {class_name}" role="img" aria-label="{html.escape(accessible)}">{rows}</div>'


def _rate(count: int, total: int) -> dict[str, float | int]:
    return {"count": count, "percent": round(_percent(count, total), 1)}


def _percent(count: int, total: int) -> float:
    return 100 * count / total if total else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = evaluate_cases(args.output_dir)
    print(json.dumps({
        "status": summary["status"],
        "materialised_results": summary["materialised_results"],
        "report": str(args.output_dir / "report.html"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
