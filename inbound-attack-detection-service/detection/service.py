"""Stdlib HTTP backend: POST /score and POST /triage.

Only the Python standard library is used (http.server). The handler
logic lives in the plain functions ``score_message_payload`` and
``triage_message_payload`` so tests can exercise it without starting a
server; the HTTP layer is a thin JSON wrapper around them.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .classifier import AttackScorer
from .triage import triage_message

_SCORER = AttackScorer()


def score_message_payload(payload: dict) -> tuple[int, dict]:
    """Validate and score a message payload. Returns (status, body)."""
    if not isinstance(payload, dict) or not payload.get("sender"):
        return 400, {"error": "payload must be an object with a 'sender' field"}
    result = _SCORER.score_message(payload)
    return 200, result


def triage_message_payload(payload: dict) -> tuple[int, dict]:
    """Score then triage a message payload. Returns (status, body)."""
    if not isinstance(payload, dict) or not payload.get("sender"):
        return 400, {"error": "payload must be an object with a 'sender' field"}
    result = _SCORER.score_message(payload)
    verdict = triage_message(payload, result)
    return 200, {"score": result, "triage": verdict}


class DetectionHandler(BaseHTTPRequestHandler):
    """JSON API handler. POST /score, POST /triage, GET /health."""

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_payload(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "unknown route"})

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        payload = self._read_payload()
        if payload is None:
            self._send_json(400, {"error": "invalid JSON object"})
            return
        if self.path == "/score":
            status, body = score_message_payload(payload)
        elif self.path == "/triage":
            status, body = triage_message_payload(payload)
        else:
            status, body = 404, {"error": "unknown route"}
        self._send_json(status, body)

    def log_message(self, *args) -> None:  # keep test output quiet
        pass


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), DetectionHandler)
    print(f"Inbound Attack Detection Service listening on http://{host}:{port}")
    print("Endpoints: POST /score, POST /triage, GET /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    run_server()
