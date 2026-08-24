#!/usr/bin/env python3
"""Run one observable JourneyBack golden path through the real HTTP pipeline."""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from journeyback.server import JourneybackHandler  # noqa: E402


CASE_ID = "JB-SYN-0331"
PRODUCT_CODE = "SG_TRUE_CASHBACK"
FIXTURE_ROOT = PROJECT_ROOT / "data" / "pipeline_test" / CASE_ID
FIXTURES = (
    {
        "path": FIXTURE_ROOT / "flight_ticket_and_itinerary.txt",
        "evidence_code": "flight_ticket",
        "note": "Verify the ticket number, route, travel dates and confirmed Card payment.",
        "marker": "TICKET_NUMBER: SYN-0331-001",
    },
    {
        "path": FIXTURE_ROOT / "carrier_confirmation.txt",
        "evidence_code": "carrier_confirmation",
        "note": "Verify the operational reason, duration and absence of an alternative within four hours.",
        "marker": "ALTERNATIVE_WITHIN_FOUR_HOURS: NO",
    },
    {
        "path": FIXTURE_ROOT / "itemised_expense_receipts.txt",
        "evidence_code": "receipts",
        "note": "Verify the itemised expenses, total amount and confirmed Card payment.",
        "marker": "TOTAL: SGD 272.00",
    },
)
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "pipeline_validation"
EXPECTED_PIPELINE = [
    "llm_fact_extraction",
    "bm25_embedding_rrf",
    "llm_grounded_guidance",
    "citation_validation",
]


class PipelineValidationError(RuntimeError):
    """Raised when a golden-path invariant is not satisfied."""


class APIClient:
    def __init__(self, base_url: str, *, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_json(self, path: str) -> dict[str, Any]:
        return self._json_request(path)

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._json_request(path, body=body)

    def _json_request(self, path: str, *, body: bytes | None = None) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"} if body is not None else {},
            method="POST" if body is not None else "GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PipelineValidationError(
                f"{request.method} {path} returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise PipelineValidationError(
                f"{request.method} {path} could not reach {self.base_url}: {exc}"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PipelineValidationError(
                f"{request.method} {path} did not return valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise PipelineValidationError(f"{request.method} {path} returned a non-object payload")
        return payload


class ValidationRun:
    def __init__(self, *, base_url: str) -> None:
        self.started = time.perf_counter()
        self.report: dict[str, Any] = {
            "evaluation_scope": "single curated end-to-end pipeline golden path",
            "case_id": CASE_ID,
            "fixtures": [
                str(item["path"].relative_to(PROJECT_ROOT)) for item in FIXTURES
            ],
            "base_url": base_url,
            "status": "running",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pipeline": EXPECTED_PIPELINE,
            "stages": [],
            "limitations": [
                "This verifies pipeline plumbing and safety invariants for one synthetic case; it is not a model benchmark.",
                "Live model wording may vary, so the test checks grounded citations and observable state changes rather than exact prose.",
                "A passing result does not approve a claim or establish real-world benefit eligibility.",
            ],
        }

    def stage(
        self,
        stage_id: str,
        label: str,
        callback: Callable[[], tuple[Any, dict[str, Any]]],
    ) -> Any:
        started = time.perf_counter()
        try:
            value, details = callback()
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1_000, 1)
            self.report["stages"].append({
                "id": stage_id,
                "label": label,
                "status": "failed",
                "duration_ms": elapsed,
                "details": {"error": str(exc)},
            })
            print(f"[FAIL] {label} · {elapsed:.1f} ms\n       {exc}")
            raise
        elapsed = round((time.perf_counter() - started) * 1_000, 1)
        self.report["stages"].append({
            "id": stage_id,
            "label": label,
            "status": "passed",
            "duration_ms": elapsed,
            "details": details,
        })
        print(f"[PASS] {label} · {elapsed:.1f} ms")
        return value

    def finish(self, *, error: Exception | None = None) -> None:
        self.report["status"] = "failed" if error else "passed"
        self.report["duration_ms"] = round((time.perf_counter() - self.started) * 1_000, 1)
        if error:
            self.report["error"] = str(error)

    def write(self, output: Path) -> None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "latest.json").write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "latest.html").write_text(_render_html(self.report), encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineValidationError(message)


def run_validation(client: APIClient, run: ValidationRun) -> None:
    def service_ready() -> tuple[dict[str, Any], dict[str, Any]]:
        health = client.get_json("/api/health")
        _require(health.get("status") == "ok", "JourneyBack health status is not ok")
        _require(health.get("ready") is True, "The live text and embedding APIs are not configured")
        llm = health.get("llm", {})
        _require(llm.get("embedding_model") == "BAAI/bge-m3", "The configured embedding model is not BAAI/bge-m3")
        return health, {
            "text_model": llm.get("model"),
            "embedding_model": llm.get("embedding_model"),
            "knowledge_chunks": health.get("knowledge_base", {}).get("chunks"),
        }

    run.stage("service_ready", "Service and BGE-M3 configuration", service_ready)

    def load_case() -> tuple[dict[str, Any], dict[str, Any]]:
        trip = client.get_json(f"/api/trip?case_id={CASE_ID}")
        _require(trip.get("case_id") == CASE_ID, "The requested synthetic case was not loaded")
        _require(trip.get("card", {}).get("product_code") == PRODUCT_CODE, "The golden-path Card product changed")
        _require(trip.get("card", {}).get("payment_verified") is True, "The golden-path Card payment is not verified")
        detected = client.post_json("/api/detect", {"case_id": CASE_ID, "live": False})
        question = detected.get("workspace", {}).get("primary_question", {})
        _require(question.get("type") == "upload", "The expected upload step is not the primary question")
        _require(question.get("evidence_code") == "flight_ticket", "The golden path no longer asks for a flight ticket")
        return detected, {
            "processing_mode": detected.get("processing_mode"),
            "blocking_input": question.get("title"),
            "flight_ticket_status": "required",
        }

    detected = run.stage("case_loaded", "Case loaded with one known evidence gap", load_case)

    def upload_fixtures() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        uploads: list[dict[str, Any]] = []
        for fixture in FIXTURES:
            path = fixture["path"]
            content = path.read_bytes()
            uploaded = client.post_json("/api/evidence", {
                "case_id": CASE_ID,
                "evidence_code": fixture["evidence_code"],
                "file_name": path.name,
                "mime_type": "text/plain",
                "content_base64": base64.b64encode(content).decode("ascii"),
                "evidence_note": fixture["note"],
            })
            inspection = uploaded.get("inspection", {})
            _require(str(uploaded.get("upload_id", "")).startswith("UP-"), f"The server did not persist {path.name}")
            _require(inspection.get("integrity_verified") is True, f"The integrity check failed for {path.name}")
            _require(inspection.get("text_extracted") is True, f"TXT extraction failed for {path.name}")
            excerpt = str(inspection.get("excerpt", ""))
            _require(CASE_ID in excerpt and fixture["marker"] in excerpt, f"Extracted text does not match {path.name}")
            uploads.append(uploaded)
        return uploads, {
            "files": [item["path"].name for item in FIXTURES],
            "upload_ids": [item.get("upload_id") for item in uploads],
            "total_bytes": sum(int(item.get("size_bytes", 0)) for item in uploads),
            "text_extracted": f"{len(uploads)}/{len(FIXTURES)}",
        }

    uploads = run.stage("evidence_uploaded", "Three TXT evidence files persisted and read", upload_fixtures)
    upload_ids = [item["upload_id"] for item in uploads]

    def live_reanalysis() -> tuple[dict[str, Any], dict[str, Any]]:
        result = client.post_json("/api/reanalyse", {
            "case_id": CASE_ID,
            "product_code": PRODUCT_CODE,
            "evidence_upload_ids": upload_ids,
        })
        trace = result.get("trace", {})
        _require(result.get("processing_mode") == "live_llm_rag", "The request did not run the live LLM/RAG path")
        _require(trace.get("pipeline") == EXPECTED_PIPELINE, "The returned trace does not match the expected pipeline")
        _require(trace.get("embedding_model") == "BAAI/bge-m3", "Live retrieval did not use BAAI/bge-m3")
        _require(int(trace.get("retrieved_chunks", 0)) > 0, "Policy retrieval returned no chunks")
        _require(int(trace.get("validated_citations", 0)) > 0, "The grounded analysis returned no validated citation")
        submitted = result.get("submitted_information", {}).get("evidence", [])
        _require(len(submitted) == len(FIXTURES), "The complete evidence set did not reach reanalysis")
        items = {item.get("code"): item for item in result.get("claim_pack", {}).get("items", [])}
        _require(items.get("flight_ticket", {}).get("status") == "complete", "The flight-ticket gap did not change to complete")
        missing_information = [
            str(value) for value in result.get("missing_information", [])
        ]
        invalid_missing_phrases = (
            "terms and conditions",
            "benefit",
            "coverage",
            "covered",
            "eligible",
            "eligibility",
            "enrolled",
            "limit",
            "threshold",
            "flight ticket",
            "itinerary",
            "carrier confirmation",
            "carrier written confirmation",
            "receipt",
            "alternative flight",
            "round-trip payment",
            "policy wording",
            "policy section",
            "coverage trigger",
            "benefit limit",
            "claim submission deadline",
            "claim submission",
            "eligible expense",
            "policy certificate",
            "policy",
        )
        invalid_requests = [
            item
            for item in missing_information
            if any(phrase in item.lower() for phrase in invalid_missing_phrases)
        ]
        _require(
            not invalid_requests,
            "The live model routed a verified fact or policy question back to the customer: "
            + "; ".join(invalid_requests),
        )
        _require(result.get("human_review_required") is True, "The safety boundary requiring human review was lost")
        policy_evidence = result.get("benefit_match", {}).get("policy_evidence", [])
        _require(
            policy_evidence
            and all(item.get("product_code") == PRODUCT_CODE for item in policy_evidence),
            "A validated citation belongs to a different Card product",
        )
        return result, {
            "model": trace.get("model"),
            "embedding_model": trace.get("embedding_model"),
            "retrieved_chunks": trace.get("retrieved_chunks"),
            "validated_citations": trace.get("validated_citations"),
            "policy_sources": len(policy_evidence),
            "policy_product": PRODUCT_CODE,
            "flight_ticket_status": "complete",
            "additional_model_questions": len(missing_information),
            "policy_questions_filtered": len(trace.get("filtered_missing_information", [])),
            "response_time_ms": result.get("response_time_ms"),
        }

    recovery = run.stage("live_reanalysis", "LLM + BGE-M3 grounded reanalysis", live_reanalysis)

    def review_pack() -> tuple[dict[str, Any], dict[str, Any]]:
        artifact = client.post_json("/api/action", {
            "case_id": CASE_ID,
            "product_code": PRODUCT_CODE,
            "evidence_upload_ids": upload_ids,
            "action_code": "build_evidence_pack",
        })
        _require(artifact.get("status") == "created", "The review pack was not created")
        pack = client.get_json(str(artifact.get("download_path", "")))
        _require(pack.get("case_id") == CASE_ID, "The downloaded review pack belongs to another case")
        _require(pack.get("status") == "draft_for_formal_review", "The artifact is not a formal-review draft")
        evidence = pack.get("submitted_evidence", [])
        _require(len(evidence) == len(FIXTURES), "The review pack does not contain the complete evidence set")
        _require(
            {item.get("sha256") for item in evidence}
            == {item.get("sha256") for item in uploads},
            "A review-pack evidence hash changed",
        )
        _require(
            pack.get("guidance", {}).get("headline")
            == recovery.get("benefit_match", {}).get("headline"),
            "The review pack did not reuse the live guidance",
        )
        _require(
            pack.get("remaining_information") == recovery.get("missing_information"),
            "The review pack lost the live model's remaining-information list",
        )
        return pack, {
            "artifact_id": artifact.get("artifact_id"),
            "submitted_evidence": len(evidence),
            "policy_sources": len(pack.get("policy_evidence", [])),
            "remaining_information": len(pack.get("remaining_information", [])),
            "live_result_reused": True,
        }

    run.stage("review_pack", "Server-backed review pack generated", review_pack)
    run.report["before_after"] = {
        "blocking_input_before": detected.get("workspace", {}).get("primary_question", {}).get("title"),
        "flight_ticket_after": "complete",
        "live_guidance_status": recovery.get("benefit_match", {}).get("status"),
    }


def _render_html(report: dict[str, Any]) -> str:
    passed = report.get("status") == "passed"
    status_label = "PIPELINE PASSED" if passed else "PIPELINE FAILED"
    stage_cards = []
    for index, stage in enumerate(report.get("stages", []), start=1):
        details = "".join(
            f"<dt>{html.escape(str(key).replace('_', ' '))}</dt><dd>{html.escape(str(value))}</dd>"
            for key, value in stage.get("details", {}).items()
        )
        stage_cards.append(
            f'<article class="{stage["status"]}"><span>{index}</span><div><small>{html.escape(stage["status"].upper())} · {stage["duration_ms"]} ms</small>'
            f'<h2>{html.escape(stage["label"])}</h2><dl>{details}</dl></div></article>'
        )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in report.get("limitations", []))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JourneyBack pipeline validation</title>
<style>
:root{{--navy:#082744;--blue:#006fcf;--green:#18794e;--red:#b42318;--ink:#173044;--muted:#657b8b;--line:#d7e0e6;--bg:#f3f6f8}}*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--bg);font-family:Arial,sans-serif}}header{{padding:54px max(28px,calc((100% - 920px)/2));color:white;background:linear-gradient(120deg,#071f37,#075d95)}}header p{{margin:0;font-size:10px;font-weight:800;letter-spacing:1.3px}}h1{{margin:12px 0 8px;font:400 44px Georgia,serif}}header span{{color:#c8dfed;font-size:12px}}main{{width:min(920px,calc(100% - 32px));margin:28px auto 60px}}.summary{{display:flex;justify-content:space-between;gap:20px;padding:20px;border-left:5px solid {"var(--green)" if passed else "var(--red)"};background:white}}.summary strong{{color:{"var(--green)" if passed else "var(--red)"}}}.summary span{{color:var(--muted);font-size:11px}}.flow{{display:grid;gap:12px;margin:20px 0}}article{{display:grid;grid-template-columns:38px 1fr;gap:15px;padding:18px;border:1px solid var(--line);background:white}}article>span{{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;color:white;background:var(--green);font-weight:800}}article.failed>span{{background:var(--red)}}article small{{color:var(--green);font-size:9px;font-weight:800}}article.failed small{{color:var(--red)}}article h2{{margin:5px 0 12px;font:400 20px Georgia,serif}}dl{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 16px;margin:0}}dt{{color:var(--muted);font-size:8px;text-transform:uppercase}}dd{{margin:2px 0 8px;font-size:10px;font-weight:700}}section{{padding:20px;border:1px solid var(--line);background:white}}section h2{{font:400 22px Georgia,serif}}li{{margin:8px 0;color:var(--muted);font-size:11px;line-height:1.5}}@media(max-width:620px){{h1{{font-size:34px}}.summary{{display:grid}}dl{{grid-template-columns:1fr}}}}
</style></head><body>
<header><p>JOURNEYBACK · END-TO-END VALIDATION</p><h1>One case. Three files. Every pipeline stage.</h1><span>{html.escape(str(report.get("case_id")))} · curated readable evidence set</span></header>
<main><div class="summary"><strong>{status_label}</strong><span>{report.get("duration_ms", 0)} ms total · {len(report.get("stages", []))}/5 stages observed</span></div>
<div class="flow">{"".join(stage_cards)}</div><section><h2>What this result means</h2><ul>{limitations}</ul></section></main></body></html>"""


def _start_local_server() -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), JourneybackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help="Test an already-running JourneyBack server instead of starting a temporary one.",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Timeout per HTTP stage in seconds.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None
    if args.base_url:
        base_url = args.base_url
    else:
        server, thread, base_url = _start_local_server()

    run = ValidationRun(base_url=base_url)
    error: Exception | None = None
    try:
        run_validation(APIClient(base_url, timeout=args.timeout), run)
    except Exception as exc:
        error = exc
    finally:
        run.finish(error=error)
        run.write(args.output)
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)

    print()
    print(f"Result: {run.report['status'].upper()} · {run.report['duration_ms']} ms")
    print(f"JSON: {args.output / 'latest.json'}")
    print(f"HTML: {args.output / 'latest.html'}")
    if error:
        print(f"Reason: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
