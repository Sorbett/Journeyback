#!/usr/bin/env python3
"""Build the product-outcome-first JourneyBack benchmark report."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "product_evaluation"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_product_report(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Combine existing evidence without turning proxy metrics into business claims."""

    synthetic = _read_json(PROJECT_ROOT / "outputs" / "synthetic_evaluation" / "summary.json")
    retrieval = _read_json(PROJECT_ROOT / "outputs" / "retrieval_evaluation" / "metrics.json")
    live = _read_json(PROJECT_ROOT / "outputs" / "mvp_evaluation" / "metrics.json")
    pipeline = _read_json(PROJECT_ROOT / "outputs" / "pipeline_validation" / "latest.json")

    metrics = synthetic.get("metrics", {})
    stages = pipeline.get("stages", [])
    stage_by_id = {
        str(stage.get("id")): stage for stage in stages if isinstance(stage, dict)
    }
    review_stage = stage_by_id.get("review_pack", {})
    review_details = review_stage.get("details", {})
    pipeline_complete = pipeline.get("status") == "passed" and len(stages) == 5
    pipeline_seconds = round(float(pipeline.get("duration_ms", 0)) / 1000, 1)

    systems = retrieval.get("systems", {})
    hybrid = systems.get("hybrid", {}) if isinstance(systems, dict) else {}
    hybrid_metrics = hybrid.get("metrics", {})

    product_scorecard = [
        {
            "outcome": "First-pass evidence readiness",
            "problem": "Travellers should know what is missing before formal review starts.",
            "current": (
                f"One curated case packaged {review_details.get('submitted_evidence', 0)} files; "
                f"{review_details.get('remaining_information', 0)} follow-up fact remains"
                if pipeline_complete
                else "Golden-path run is incomplete"
            ),
            "target": "+25 percentage points vs static form",
            "status": "proxy" if pipeline_complete else "unmeasured",
        },
        {
            "outcome": "Time to a review-ready pack",
            "problem": "Reduce effort for both the traveller and the specialist.",
            "current": f"{pipeline_seconds:.1f}s on one curated case" if pipeline_complete else "Not measured",
            "target": "40% lower median task time",
            "status": "proxy" if pipeline_complete else "unmeasured",
        },
        {
            "outcome": "Follow-up burden",
            "problem": "Avoid repeated requests for documents and policy facts.",
            "current": "Not measured against a manual workflow",
            "target": "30% fewer follow-up interactions",
            "status": "unmeasured",
        },
        {
            "outcome": "Specialist acceptance",
            "problem": "The generated pack must be useful, not merely complete.",
            "current": "No blinded reviewer study yet",
            "target": "At least 80% accepted without rework",
            "status": "unmeasured",
        },
        {
            "outcome": "Safe human handoff",
            "problem": "Never trade speed for policy leakage or payout promises.",
            "current": (
                f"{metrics.get('human_review_guardrail', {}).get('percent', 0):.1f}% guardrail coverage on synthetic expected paths"
            ),
            "target": "0 critical safety violations",
            "status": "proxy",
        },
    ]

    report = {
        "evaluation_scope": "JourneyBack product outcome benchmark",
        "status": "baseline_study_required",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "product_value_score": None,
        "score_reason": "A product-value score requires a manual-workflow baseline and blinded human review.",
        "current_evidence": {
            "synthetic_scenarios": int(synthetic.get("dataset_size", 0)),
            "evidence_gap_scenarios": int(metrics.get("missing_key_documents", {}).get("count", 0)),
            "evidence_gap_percent": float(metrics.get("missing_key_documents", {}).get("percent", 0)),
            "non_english_scenarios": int(metrics.get("non_english_cases", {}).get("count", 0)),
            "pipeline_stages_passed": sum(stage.get("status") == "passed" for stage in stages),
            "pipeline_stages_total": 5,
            "pipeline_seconds": pipeline_seconds if pipeline_complete else None,
            "live_smoke_cases": int(live.get("completed_cases", 0)),
            "live_average_latency_seconds": live.get("metrics", {}).get("average_latency_seconds"),
        },
        "product_scorecard": product_scorecard,
        "algorithm_support": {
            "retrieval_queries": int(retrieval.get("holdout", {}).get("queries", 0)),
            "system": hybrid.get("label", "Hybrid retrieval"),
            "recall_at_5": hybrid_metrics.get("recall_at_5"),
            "mrr_at_10": hybrid_metrics.get("mrr_at_10"),
            "ndcg_at_5": hybrid_metrics.get("ndcg_at_5"),
        },
        "evaluation_design": [
            "Static claim form or checklist",
            "General-purpose LLM without retrieval",
            "Policy retrieval without the evidence workflow",
            "JourneyBack evidence workflow with grounded retrieval",
        ],
        "limitations": [
            "The 600 synthetic cases measure designed scenario coverage, not real-world incidence or business uplift.",
            "The current complete evidence workflow has one curated golden case and is not a generalisation result.",
            "Retrieval accuracy supports product quality but is not itself a customer-value metric.",
            "Time saved, fewer follow-ups and reviewer acceptance require a controlled baseline study.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "report.html").write_text(_render_html(report), encoding="utf-8")
    return report


def _render_html(report: dict[str, Any]) -> str:
    evidence = report["current_evidence"]
    algorithm = report["algorithm_support"]
    pipeline_passed = evidence["pipeline_stages_passed"]
    pipeline_total = evidence["pipeline_stages_total"]
    pipeline_time = evidence["pipeline_seconds"]
    score_rows = "".join(
        f"""
        <tr>
          <td><strong>{html.escape(item['outcome'])}</strong><small>{html.escape(item['problem'])}</small></td>
          <td>{html.escape(item['current'])}<span class="state {item['status']}">{'Current proxy' if item['status'] == 'proxy' else 'Needs baseline'}</span></td>
          <td>{html.escape(item['target'])}</td>
        </tr>"""
        for item in report["product_scorecard"]
    )
    arms = "".join(
        f"<li><span>0{index}</span>{html.escape(label)}</li>"
        for index, label in enumerate(report["evaluation_design"], start=1)
    )
    limitations = "".join(
        f"<li>{html.escape(item)}</li>" for item in report["limitations"]
    )

    def percent(value: Any) -> str:
        return "—" if value is None else f"{float(value) * 100:.1f}%"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>JourneyBack product benchmark</title>
  <style>
    :root{{--navy:#071f37;--navy2:#0b3358;--blue:#006fcf;--sky:#dff3ff;--green:#16734b;--amber:#a96500;--ink:#172d40;--muted:#64798a;--line:#d8e2e8;--bg:#f3f6f8;--white:#fff;font-family:Inter,"Helvetica Neue",Arial,sans-serif;color:var(--ink);background:var(--bg)}}
    *{{box-sizing:border-box}}body{{margin:0}}a{{color:inherit}}header{{padding:28px max(24px,calc((100% - 1160px)/2)) 62px;color:white;background:linear-gradient(118deg,var(--navy),#075b93)}}
    .nav{{display:flex;align-items:center;justify-content:space-between;margin-bottom:70px}}.brand{{font-weight:800;text-decoration:none}}.nav-links{{display:flex;gap:22px;font-size:10px}}.nav-links a{{color:#c7ddec;text-decoration:none}}
    .kicker{{margin:0 0 13px;color:#83caef;font-size:9px;font-weight:800;letter-spacing:1.3px}}h1{{max-width:850px;margin:0;font:400 clamp(37px,5vw,61px)/1.03 Georgia,serif}}
    .lead{{max-width:730px;margin:18px 0 0;color:#c7ddec;font-size:13px;line-height:1.65}}.verdict{{display:flex;align-items:center;gap:13px;margin-top:28px}}.verdict strong{{padding:8px 10px;color:#3d2700;background:#ffd77f;font-size:9px}}.verdict span{{color:#bcd4e4;font-size:10px}}
    main{{width:min(1160px,calc(100% - 42px));margin:0 auto;padding:36px 0 70px}}.evidence-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-bottom:54px;background:var(--line);border:1px solid var(--line)}}
    .evidence-card{{min-height:155px;padding:23px;background:white}}.evidence-card strong{{display:block;color:var(--navy);font:400 39px Georgia,serif}}.evidence-card span{{display:block;margin:8px 0 5px;font-size:10px;font-weight:800}}.evidence-card small{{color:var(--muted);font-size:9px;line-height:1.5}}
    .section-head{{display:grid;grid-template-columns:.9fr 1.1fr;gap:70px;align-items:end;margin:55px 0 22px}}h2{{margin:0;color:var(--navy);font:400 31px Georgia,serif}}.section-head p{{margin:0;color:var(--muted);font-size:11px;line-height:1.65}}
    .scorecard{{width:100%;border-collapse:collapse;background:white;border:1px solid var(--line)}}th,td{{padding:16px 18px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.7px}}td{{font-size:10px;line-height:1.5}}td strong,td small{{display:block}}td strong{{margin-bottom:4px;color:var(--navy);font-size:11px}}td small{{max-width:380px;color:var(--muted)}}.state{{display:block;width:max-content;margin-top:8px;padding:4px 6px;font-size:7px;font-weight:800;text-transform:uppercase}}.state.proxy{{color:var(--green);background:#e9f7ef}}.state.unmeasured{{color:var(--amber);background:#fff3d7}}
    .study{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.study>div,.algorithm{{padding:25px;border:1px solid var(--line);background:white}}.study h3,.algorithm h3{{margin:0 0 8px;color:var(--navy);font:400 22px Georgia,serif}}.study p,.algorithm p{{margin:0;color:var(--muted);font-size:10px;line-height:1.6}}.arms{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:22px 0 0;padding:0;list-style:none}}.arms li{{display:grid;grid-template-columns:29px 1fr;gap:9px;align-items:center;min-height:54px;padding:9px;background:#f6f9fb;font-size:9px}}.arms span{{display:grid;place-items:center;width:27px;height:27px;color:white;background:var(--blue);font-size:8px;font-weight:800}}
    .algorithm-metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-top:22px;background:var(--line)}}.algorithm-metrics div{{padding:17px;background:#f8fbfd}}.algorithm-metrics strong,.algorithm-metrics span{{display:block}}.algorithm-metrics strong{{color:var(--navy);font:400 25px Georgia,serif}}.algorithm-metrics span{{margin-top:5px;color:var(--muted);font-size:8px}}
    .limitations{{margin-top:26px;padding:22px 26px;color:#d5e4ee;background:var(--navy)}}.limitations strong{{font-size:10px}}.limitations ul{{margin:13px 0 0;padding-left:17px}}.limitations li{{margin:6px 0;font-size:9px;line-height:1.5}}
    footer{{padding:24px max(24px,calc((100% - 1160px)/2));color:#738694;background:white;font-size:8px}}
    @media(max-width:820px){{.evidence-grid{{grid-template-columns:1fr 1fr}}.section-head,.study{{grid-template-columns:1fr;gap:16px}}.scorecard{{display:block;overflow-x:auto}}}}
    @media(max-width:520px){{.nav-links{{display:none}}.evidence-grid,.arms{{grid-template-columns:1fr}}.algorithm-metrics{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>
  <header>
    <div class="nav"><a class="brand" href="/">JourneyBack</a><div class="nav-links"><a href="/">Product demo</a><a href="/evaluation/scenarios">Scenario coverage</a><a href="/evaluation/retrieval">Algorithm evidence</a></div></div>
    <p class="kicker">PRODUCT OUTCOME BENCHMARK</p>
    <h1>Does JourneyBack make disrupted travel easier to resolve?</h1>
    <p class="lead">The primary benchmark is customer and specialist progress: a clearer next step, a more complete evidence pack, fewer follow-ups and a safe handoff. Retrieval quality is supporting evidence—not the product score.</p>
    <div class="verdict"><strong>PRODUCT VALUE SCORE · NOT YET CLAIMED</strong><span>{html.escape(report['score_reason'])}</span></div>
  </header>
  <main>
    <section class="evidence-grid" aria-label="Evidence available today">
      <article class="evidence-card"><strong>{evidence['synthetic_scenarios']}</strong><span>designed travel scenarios</span><small>Coverage of the intended problem space, not real-world incidence.</small></article>
      <article class="evidence-card"><strong>{evidence['evidence_gap_scenarios']}</strong><span>evidence-gap scenarios</span><small>{evidence['evidence_gap_percent']:.1f}% test document collection and recovery prompts.</small></article>
      <article class="evidence-card"><strong>{pipeline_passed}/{pipeline_total}</strong><span>end-to-end stages passed</span><small>{f'{pipeline_time:.1f}s on the curated evidence pack.' if pipeline_time is not None else 'Run the complete golden path to refresh this result.'}</small></article>
      <article class="evidence-card"><strong>—</strong><span>business uplift</span><small>Requires a static-form baseline and human reviewers.</small></article>
    </section>

    <section>
      <div class="section-head"><h2>Product outcomes come first</h2><p>The benchmark should reward JourneyBack only when it removes real work. Proxy evidence is shown, but no uplift is claimed until the same cases are completed through a baseline workflow.</p></div>
      <table class="scorecard"><thead><tr><th>Product outcome</th><th>Evidence today</th><th>Pass threshold</th></tr></thead><tbody>{score_rows}</tbody></table>
    </section>

    <section>
      <div class="section-head"><h2>How the value test should run</h2><p>Use sealed, document-complete cases and compare the full task—not isolated model responses. Reviewers should be blinded to the system used.</p></div>
      <div class="study">
        <div><h3>Four matched workflows</h3><p>The same cases, documents and policy versions must be used in every arm.</p><ol class="arms">{arms}</ol></div>
        <div class="algorithm"><h3>Algorithm evidence · supporting layer</h3><p>{algorithm['retrieval_queries']} author-reviewed English and Chinese queries · {html.escape(str(algorithm['system']))}</p><div class="algorithm-metrics"><div><strong>{percent(algorithm['recall_at_5'])}</strong><span>Recall@5</span></div><div><strong>{percent(algorithm['mrr_at_10'])}</strong><span>MRR@10</span></div><div><strong>{percent(algorithm['ndcg_at_5'])}</strong><span>nDCG@5</span></div></div></div>
      </div>
    </section>

    <aside class="limitations"><strong>READ THE EVIDENCE HONESTLY</strong><ul>{limitations}</ul></aside>
  </main>
  <footer>JourneyBack product benchmark · Generated by scripts/evaluate_product.py · Product outcomes precede component metrics.</footer>
</body>
</html>"""


def main() -> None:
    report = build_product_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
