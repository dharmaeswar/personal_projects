"""HTTP API over the three primitives (stdlib only, no framework).

Routes:
  POST /users            {"email", "name"}            -> create a user (store)
  GET  /users/<id>/events                          -> user events (store)
  POST /enqueue          {"kind", ...}              -> enqueue a task (queue)
  POST /lease            {"batch": n}               -> lease tasks (queue)
  POST /ack              {"id": n}                  -> ack a task (queue)
  POST /kv/<key>         {"value", "ttl_s", ...}    -> put a KV entry
  GET  /kv/<key>                                     -> get a KV entry
  GET  /kv?prefix=...                               -> list KV keys
  GET  /metrics                                     -> metrics summary + alerts
Every request is timed and recorded in the shared Metrics object.
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .kv import KeyValueStore
from .monitoring import AlertRule, Metrics, evaluate_alerts
from .queue import MessageQueue
from .store import DurableStore


class EdgeAPI:
    """Holds the three primitives plus metrics; the HTTP handler delegates here."""

    def __init__(self, db_path: str = ":memory:"):
        self.store = DurableStore(db_path)
        self.queue = MessageQueue(db_path if db_path != ":memory:" else ":memory:")
        self.kv = KeyValueStore(db_path if db_path != ":memory:" else ":memory:")
        self.metrics = Metrics()
        self.rules = [
            AlertRule("high-error-rate", "enqueue.error_rate", 0.05),
            AlertRule("slow-lease", "lease.p95_ms", 500.0),
        ]

    def handle(self, method: str, path: str, body: dict | None) -> tuple[int, dict]:
        started = time.perf_counter()
        try:
            status, payload, op = self._route(method, path, body or {})
        except (KeyError, ValueError, TypeError) as exc:
            status, payload, op = 400, {"error": str(exc)}, "bad_request"
        self.metrics.record(op, (time.perf_counter() - started) * 1000, ok=status < 400)
        return status, payload

    def _route(self, method: str, path: str, body: dict) -> tuple[int, dict, str]:
        parsed = urlparse(path)
        parts = [p for p in parsed.path.split("/") if p]

        if method == "POST" and parts == ["users"]:
            user_id = self.store.create_user(body["email"], body["name"])
            return 201, {"id": user_id}, "create_user"
        if method == "GET" and len(parts) == 3 and parts[0] == "users" and parts[2] == "events":
            return 200, {"events": self.store.user_events(int(parts[1]))}, "user_events"
        if method == "POST" and parts == ["enqueue"]:
            msg_id = self.queue.enqueue(body)
            return 201, {"id": msg_id, "depth": self.queue.depth()}, "enqueue"
        if method == "POST" and parts == ["lease"]:
            leased = self.queue.lease(batch_size=int(body.get("batch", 10)))
            return 200, {"leased": leased}, "lease"
        if method == "POST" and parts == ["ack"]:
            self.queue.ack(int(body["id"]))
            return 200, {"acked": body["id"]}, "ack"
        if method == "POST" and len(parts) == 2 and parts[0] == "kv":
            self.kv.put(parts[1], body["value"], ttl_s=body.get("ttl_s"), metadata=body.get("metadata"))
            return 201, {"key": parts[1]}, "kv_put"
        if method == "GET" and len(parts) == 2 and parts[0] == "kv":
            value = self.kv.get(parts[1])
            return (200, {"value": value}, "kv_get") if value is not None else (404, {"error": "not found"}, "kv_get")
        if method == "GET" and parts == ["kv"]:
            query = parse_qs(parsed.query)
            result = self.kv.list_keys(prefix=query.get("prefix", [""])[0])
            return 200, result, "kv_list"
        if method == "GET" and parts == ["metrics"]:
            alerts = evaluate_alerts(
                self.metrics, self.rules, {"queue.depth": float(self.queue.depth())}
            )
            return 200, {"metrics": self.metrics.summary(), "alerts": alerts}, "metrics"
        return 404, {"error": "unknown route"}, "unknown"


def make_handler(api: EdgeAPI):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            self._send(*self._dispatch("GET"))

        def do_POST(self) -> None:  # noqa: N802 - http.server naming
            self._send(*self._dispatch("POST"))

        def _dispatch(self, method: str) -> tuple[int, dict]:
            try:
                return api.handle(method, self.path, self._read_body())
            except (KeyError, ValueError, TypeError) as exc:
                return 400, {"error": str(exc)}

        def log_message(self, *args) -> None:  # keep test output clean
            pass

    return Handler


def serve(api: EdgeAPI, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(api))


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = serve(EdgeAPI("edge.db"), port=port)
    print(f"Edge Data Primitives API on http://127.0.0.1:{port}")
    server.serve_forever()
