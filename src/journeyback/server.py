"""Small dependency-free HTTP server for the Journeyback MVP."""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .engine import JourneybackEngine
from .evidence_store import (
    DEFAULT_UPLOAD_ROOT,
    evidence_inspection,
    enrich_case,
    load_evidence,
    reanalysis_message,
    save_evidence,
)
from .llm_client import LLMAPIError, LLMConfigurationError, LLMResponseError
from .pipeline_evidence import pipeline_test_kit
from .recovery_actions import (
    create_recovery_artifact,
    load_reanalysis_snapshot,
    load_recovery_artifact,
    save_reanalysis_snapshot,
)
from .synthetic_demo import (
    dataset_insights,
    get_case,
    recovery_case_after_product_confirmation,
    recovery_case_from_synthetic,
    trip_from_case,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
PRODUCT_EVALUATION_REPORT = PROJECT_ROOT / "outputs" / "product_evaluation" / "report.html"
RETRIEVAL_EVALUATION_REPORT = PROJECT_ROOT / "outputs" / "retrieval_evaluation" / "report.html"
SYNTHETIC_EVALUATION_REPORT = PROJECT_ROOT / "outputs" / "synthetic_evaluation" / "report.html"
class JourneybackHandler(BaseHTTPRequestHandler):
    engine = JourneybackEngine()
    upload_root = DEFAULT_UPLOAD_ROOT
    static_routes = {
        "/": "index.html",
        "/index.html": "index.html",
        "/app.js": "app.js",
        "/styles.css": "styles.css",
    }

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[Journeyback] {self.address_string()} - {format_string % args}")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, filename: str) -> None:
        self._serve_file(WEB_ROOT / filename)

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _download(self, *, body: bytes, filename: str, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{Path(filename).name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/api/health":
            self._json({
                "status": "ok",
                "ready": self.engine.ready,
                "service": "journeyback-llm-mvp",
                "llm": self.engine.runtime_summary(),
                "knowledge_base": self.engine.retriever.knowledge_base.summary(),
            })
            return
        if route == "/api/config":
            self._json(self.engine.runtime_summary())
            return
        if route == "/api/trip":
            case_id = query.get("case_id", [None])[0]
            try:
                self._json(trip_from_case(get_case(case_id)))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        if route == "/api/demo/insights":
            self._json(dataset_insights())
            return
        if route == "/api/demo/pipeline-test-kit":
            case_id = str(query.get("case_id", [""])[0])
            product_code = str(query.get("product_code", [""])[0]) or None
            try:
                get_case(case_id)
                self._json(pipeline_test_kit(case_id, product_code=product_code))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            except OSError as exc:
                self._json(
                    {"error": f"Pipeline test data is unavailable: {exc}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        if route == "/api/artifact":
            case_id = str(query.get("case_id", [""])[0])
            artifact_id = str(query.get("artifact_id", [""])[0])
            try:
                metadata, body = load_recovery_artifact(
                    case_id=case_id,
                    artifact_id=artifact_id,
                    artifact_root=self.upload_root,
                )
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            self._download(
                body=body,
                filename=str(metadata["file_name"]),
                content_type=str(metadata["media_type"]),
            )
            return
        if route == "/evaluation":
            self._serve_file(PRODUCT_EVALUATION_REPORT)
            return
        if route == "/evaluation/retrieval":
            self._serve_file(RETRIEVAL_EVALUATION_REPORT)
            return
        if route == "/evaluation/scenarios":
            self._serve_file(SYNTHETIC_EVALUATION_REPORT)
            return
        if route == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if route in self.static_routes:
            self._static(self.static_routes[route])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route not in {
            "/api/detect",
            "/api/analyze",
            "/api/evaluate",
            "/api/evidence",
            "/api/product-confirmation",
            "/api/reanalyse",
            "/api/action",
        }:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            maximum_length = 2_100_000 if route == "/api/evidence" else 100_000
            if length <= 0 or length > maximum_length:
                raise ValueError(f"Request body must be between 1 and {maximum_length} bytes")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            if route == "/api/evidence":
                case_id = str(payload.get("case_id") or "")
                get_case(case_id)
                result = save_evidence(
                    case_id=case_id,
                    evidence_code=str(payload.get("evidence_code") or ""),
                    file_name=str(payload.get("file_name") or ""),
                    mime_type=str(payload.get("mime_type") or ""),
                    content_base64=str(payload.get("content_base64") or ""),
                    evidence_note=str(payload.get("evidence_note") or ""),
                    upload_root=self.upload_root,
                )
            elif route == "/api/action":
                case_id = str(payload.get("case_id") or "")
                case = get_case(case_id)
                upload_ids = payload.get("evidence_upload_ids", [])
                if not isinstance(upload_ids, list) or len(upload_ids) > 10:
                    raise ValueError("evidence_upload_ids must be a list of at most 10 ids")
                uploaded_evidence = load_evidence(
                    case_id=case_id,
                    upload_ids=[str(value) for value in upload_ids],
                    upload_root=self.upload_root,
                )
                enriched_case = enrich_case(
                    case,
                    product_code=str(payload.get("product_code") or "") or None,
                    uploaded_evidence=uploaded_evidence,
                )
                product_code = str(payload.get("product_code") or "") or None
                recovery = load_reanalysis_snapshot(
                    case_id=case_id,
                    product_code=product_code,
                    evidence_upload_ids=[str(value) for value in upload_ids],
                    artifact_root=self.upload_root,
                ) or recovery_case_from_synthetic(enriched_case)
                result = create_recovery_artifact(
                    case=enriched_case,
                    action_code=str(payload.get("action_code") or ""),
                    recovery=recovery,
                    uploaded_evidence=uploaded_evidence,
                    artifact_root=self.upload_root,
                )
            elif route == "/api/product-confirmation":
                started = time.perf_counter()
                case_id = str(payload.get("case_id") or "")
                case = get_case(case_id)
                product_code = str(payload.get("product_code") or "") or None
                if product_code is None:
                    raise ValueError("Select a product before confirming it.")
                enriched_case = enrich_case(
                    case,
                    product_code=product_code,
                    uploaded_evidence=[],
                )
                result = recovery_case_after_product_confirmation(enriched_case)
                result["response_time_ms"] = round(
                    (time.perf_counter() - started) * 1_000, 1
                )
                result["submitted_information"] = {
                    "product_code": product_code,
                    "evidence": [],
                }
                save_reanalysis_snapshot(
                    case_id=case_id,
                    product_code=product_code,
                    evidence_upload_ids=[],
                    recovery=result,
                    artifact_root=self.upload_root,
                )
            elif route == "/api/reanalyse":
                started = time.perf_counter()
                case_id = str(payload.get("case_id") or "")
                case = get_case(case_id)
                upload_ids = payload.get("evidence_upload_ids", [])
                if not isinstance(upload_ids, list) or len(upload_ids) > 10:
                    raise ValueError("evidence_upload_ids must be a list of at most 10 ids")
                product_code = str(payload.get("product_code") or "") or None
                if product_code is None and not upload_ids:
                    raise ValueError("Submit a product selection or uploaded evidence before reanalysis.")
                uploaded_evidence = load_evidence(
                    case_id=case_id,
                    upload_ids=[str(value) for value in upload_ids],
                    upload_root=self.upload_root,
                )
                enriched_case = enrich_case(
                    case,
                    product_code=product_code,
                    uploaded_evidence=uploaded_evidence,
                )
                guidance = self.engine.evaluate({
                    "message": reanalysis_message(
                        enriched_case, uploaded_evidence=uploaded_evidence
                    ),
                    "locale": "zh-SG" if case["language"] == "zh" else "en-SG",
                })
                result = recovery_case_from_synthetic(
                    enriched_case, live_guidance=guidance
                )
                result["response_time_ms"] = round(
                    (time.perf_counter() - started) * 1_000, 1
                )
                result["submitted_information"] = {
                    "product_code": product_code,
                    "evidence": [
                        {
                            "upload_id": item["upload_id"],
                            "evidence_code": item["evidence_code"],
                            "file_name": item["file_name"],
                            "mime_type": item["mime_type"],
                            "size_bytes": item["size_bytes"],
                            "inspection": evidence_inspection(item),
                        }
                        for item in uploaded_evidence
                    ],
                }
                save_reanalysis_snapshot(
                    case_id=case_id,
                    product_code=product_code,
                    evidence_upload_ids=[str(value) for value in upload_ids],
                    recovery=result,
                    artifact_root=self.upload_root,
                )
            elif route == "/api/detect":
                started = time.perf_counter()
                case = get_case(str(payload.get("case_id") or "") or None)
                live = payload.get("live") is True
                guidance = None
                if live:
                    guidance = self.engine.evaluate({
                        "message": case["user_query"],
                        "locale": "zh-SG" if case["language"] == "zh" else "en-SG",
                    })
                result = recovery_case_from_synthetic(case, live_guidance=guidance)
                result["response_time_ms"] = round((time.perf_counter() - started) * 1_000, 1)
            else:
                result = self.engine.evaluate(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except OSError as exc:
            self._json({"error": f"Evidence storage failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        except LLMConfigurationError as exc:
            self._json({"error": str(exc), "code": "llm_not_configured"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        except (LLMAPIError, LLMResponseError) as exc:
            self._json({"error": str(exc), "code": "llm_request_failed"}, HTTPStatus.BAD_GATEWAY)
            return
        self._json(result)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), JourneybackHandler)
    print(f"Journeyback MVP running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
