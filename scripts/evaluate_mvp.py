#!/usr/bin/env python3
"""Run a small live smoke evaluation of the LLM-first Journeyback pipeline."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.engine import JourneybackEngine  # noqa: E402
from journeyback.llm_client import LLMError  # noqa: E402


OUTPUT_PATH = PROJECT_ROOT / "outputs" / "mvp_evaluation" / "metrics.json"
CASES = [
    {
        "case_id": "LIVE-BAGGAGE-01",
        "message": "A round-trip itinerary paid with The Platinum Card arrived in Tokyo, but one checked bag has not been delivered seven hours after arrival. The itinerary is available but the PIR is missing.",
    },
    {
        "case_id": "LIVE-CANCEL-01",
        "message": "A return flight to Singapore paid with a KrisFlyer Ascend Card has been cancelled. The carrier says the earliest alternative is tomorrow afternoon and no hotel has been booked.",
    },
    {
        "case_id": "LIVE-MISSING-01",
        "message": "A flight is delayed, but the exact American Express Card product and the carrier's next available departure time have not been confirmed.",
    },
]


def main() -> None:
    engine = JourneybackEngine()
    if not engine.ready:
        report = {
            "evaluation_scope": "Live LLM smoke evaluation",
            "status": "not_run",
            "reason": "The text-generation and/or embedding provider API key is not configured",
            "model": engine.settings.model,
            "embedding_model": engine.settings.embedding_model,
            "offline_validation": "Run python3 -m unittest discover -s tests -v for mocked pipeline tests.",
        }
        _write(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    results = []
    for case in CASES:
        started = time.perf_counter()
        try:
            output = engine.evaluate({"message": case["message"]})
            results.append({
                "case_id": case["case_id"],
                "completed": True,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "status": output["status"],
                "validated_citations": len(output["policy_evidence"]),
                "invalid_citations_rejected": len(output["trace"]["rejected_citations"]),
                "human_review_guardrail": output["human_review_required"] is True,
                "no_expected_payout": output["expected_payout_sgd"] is None,
            })
        except LLMError as exc:
            results.append({
                "case_id": case["case_id"],
                "completed": False,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": str(exc),
            })

    completed = [item for item in results if item["completed"]]
    count = len(completed)
    report = {
        "evaluation_scope": "Live LLM smoke evaluation",
        "status": "completed" if count == len(CASES) else "partial",
        "model": engine.settings.model,
        "embedding_model": engine.settings.embedding_model,
        "test_cases": len(CASES),
        "completed_cases": count,
        "metrics": {
            "response_completion_rate": count / len(CASES),
            "validated_citation_rate": sum(item["validated_citations"] > 0 for item in completed) / count if count else 0,
            "human_review_guardrail_rate": sum(item["human_review_guardrail"] for item in completed) / count if count else 0,
            "no_payout_prediction_rate": sum(item["no_expected_payout"] for item in completed) / count if count else 0,
            "average_latency_seconds": round(sum(item["latency_seconds"] for item in completed) / count, 3) if count else None,
        },
        "results": results,
        "limitations": [
            "This is an API and grounding smoke test, not a claim-eligibility accuracy score.",
            "Business quality requires human-labelled cases and review by policy owners.",
            "Public policy documents must be checked for currency before production use.",
        ],
    }
    _write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _write(report: dict[str, object]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
