"""Small dependency-free HTTP server for the Journeyback MVP."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .engine import JourneybackEngine
from .demo_trip import build_recovery_case, disruption_event_message, trip_snapshot
from .llm_client import LLMAPIError, LLMConfigurationError, LLMResponseError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"


class JourneybackHandler(BaseHTTPRequestHandler):
    engine = JourneybackEngine()
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
        path = WEB_ROOT / filename
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

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
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
            self._json(trip_snapshot())
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
        if route not in {"/api/detect", "/api/analyze", "/api/evaluate"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100_000:
                raise ValueError("Request body must be between 1 and 100000 bytes")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if route == "/api/detect":
                trip = trip_snapshot(disruption_detected=True)
                guidance = self.engine.evaluate({
                    "message": disruption_event_message(trip),
                    "locale": "en-SG",
                })
                result = build_recovery_case(trip, guidance)
            else:
                result = self.engine.evaluate(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
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
