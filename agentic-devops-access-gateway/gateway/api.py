"""Stdlib-only HTTP surface for the access gateway.

Endpoints (all JSON):
- GET  /health            -- liveness, no auth
- GET  /v1/servers        -- registered remote servers (Bearer token)
- GET  /v1/audit          -- audit log entries (Bearer token)
- POST /v1/execute        -- run an agent action through the gateway
  body: {"action", "resource", "server_id", "idempotency_key"?}
  Bearer token in the Authorization header.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .gateway import AccessGateway


def make_handler(gateway: AccessGateway):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output quiet
            pass

        def _send(self, status: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _bearer(self) -> str:
            auth = self.headers.get("Authorization", "")
            return auth[len("Bearer "):] if auth.startswith("Bearer ") else ""

        def _require_token(self):
            token = self._bearer()
            if not token:
                return None
            try:
                return gateway.tokens.verify(token)
            except ValueError:
                return None

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"status": "ok"})
            record = self._require_token()
            if record is None:
                return self._send(401, {"error": "missing or invalid token"})
            if self.path == "/v1/servers":
                servers = [{"server_id": s.server_id, "name": s.name,
                            "environment": s.environment, "endpoint": s.endpoint,
                            "healthy": s.healthy}
                           for s in gateway.registry.list()]
                return self._send(200, {"servers": servers})
            if self.path == "/v1/audit":
                entries = [{"seq": e.seq, "actor": e.actor, "action": e.action,
                            "resource": e.resource, "server_id": e.server_id,
                            "decision": e.decision, "reason": e.reason}
                           for e in gateway.audit.entries()]
                return self._send(200, {"entries": entries})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/execute":
                return self._send(404, {"error": "not found"})
            token = self._bearer()
            if not token:
                return self._send(401, {"error": "missing token"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                result = gateway.execute(
                    token, body["action"], body["resource"], body["server_id"],
                    idempotency_key=body.get("idempotency_key"))
            except KeyError as exc:
                return self._send(400, {"error": f"missing field {exc}"})
            except json.JSONDecodeError:
                return self._send(400, {"error": "invalid JSON"})
            status = 200 if result.allowed else 403
            return self._send(status, {"allowed": result.allowed,
                                       "reason": result.reason,
                                       "result": result.result,
                                       "replayed": result.replayed})

    return Handler


def serve(gateway: AccessGateway, host: str = "127.0.0.1", port: int = 8000):
    return ThreadingHTTPServer((host, port), make_handler(gateway))
