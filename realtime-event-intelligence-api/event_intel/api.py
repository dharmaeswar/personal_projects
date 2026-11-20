"""HTTP API for the event intelligence service (stdlib http.server).

Endpoints:
- GET  /health            liveness check, no auth
- POST /v1/events         ingest one signal (scope events:write)
- GET  /v1/alerts         list alerts, ?min_severity=N (scope alerts:read)
- GET  /v1/alerts/{id}    fetch one alert (scope alerts:read)

Signal body for POST /v1/events:
{"source_id": str, "event_type": str, "text": str,
 "reliability": 0-1, "keyword_severity": 0-1,
 "corroborations": int, "age_seconds": float}
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .auth import AuthError, TokenStore, bearer_from_header
from .scoring import WATCH_THRESHOLD, band, score_event
from .store import EventStore


def make_handler(store: EventStore, tokens: TokenStore):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test output quiet
            pass

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _require_scope(self, scope: str) -> bool:
            try:
                tokens.validate(
                    bearer_from_header(self.headers.get("Authorization")), scope
                )
            except AuthError as exc:
                self._send(401, {"error": str(exc)})
                return False
            return True

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return None
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(200, {"status": "ok", **store.counts()})
                return
            if parsed.path == "/v1/alerts":
                if not self._require_scope("alerts:read"):
                    return
                query = parse_qs(parsed.query)
                try:
                    min_severity = float(query.get("min_severity", ["0"])[0])
                except ValueError:
                    self._send(400, {"error": "min_severity must be a number"})
                    return
                self._send(200, {"alerts": store.list_alerts(min_severity)})
                return
            if parsed.path.startswith("/v1/alerts/"):
                if not self._require_scope("alerts:read"):
                    return
                try:
                    alert_id = int(parsed.path.rsplit("/", 1)[-1])
                except ValueError:
                    self._send(400, {"error": "alert id must be an integer"})
                    return
                alert = store.get_alert(alert_id)
                if alert is None:
                    self._send(404, {"error": "alert not found"})
                    return
                self._send(200, alert)
                return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/v1/events":
                self._send(404, {"error": "not found"})
                return
            if not self._require_scope("events:write"):
                return
            body = self._read_json()
            if not isinstance(body, dict):
                self._send(400, {"error": "JSON object body required"})
                return
            required = ("source_id", "event_type", "text")
            missing = [k for k in required if not body.get(k)]
            if missing:
                self._send(400, {"error": f"missing fields: {', '.join(missing)}"})
                return
            try:
                score = score_event(
                    reliability=float(body.get("reliability", 0.5)),
                    keyword_severity=float(body.get("keyword_severity", 0.5)),
                    corroborations=int(body.get("corroborations", 0)),
                    age_seconds=float(body.get("age_seconds", 0.0)),
                )
            except (TypeError, ValueError) as exc:
                self._send(400, {"error": str(exc)})
                return
            result = store.ingest(
                source_id=str(body["source_id"]),
                event_type=str(body["event_type"]),
                text=str(body["text"]),
                score=score,
                band_name=band(score),
            )
            status = 200 if result["status"] == "duplicate" else 201
            self._send(status, {**result, "score": score, "band": band(score)})

    return Handler


def run(port: int = 8000, store: EventStore | None = None, tokens: TokenStore | None = None):
    """Serve the API forever on 127.0.0.1:port."""
    store = store or EventStore()
    tokens = tokens or TokenStore()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, tokens))
    print(f"listening on http://127.0.0.1:{port}")
    print("health: GET /health (no auth)")
    print("demo read token:", tokens.mint_token(["alerts:read"]))
    print("demo write token:", tokens.mint_token(["events:write"]))
    server.serve_forever()
