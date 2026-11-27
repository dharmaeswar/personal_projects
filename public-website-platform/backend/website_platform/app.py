"""Public website platform API.

Python standard library only — no web framework. Serves the content,
forms, analytics, and consent endpoints a public marketing website needs:

- GET  /health
- GET  /api/content/pages, GET /api/content/pages/{slug}
- POST /api/forms/{form_id}/submissions  (validation, idempotency key)
- POST /api/analytics/events             (consent-gated batch intake)
- GET  /api/consent?visitor_id=...  POST /api/consent
- GET  /metrics  (Prometheus-format text)
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from website_platform.store import Store

STORE = Store()
MAX_BODY_BYTES = 64 * 1024
MAX_EVENTS_PER_BATCH = 50


def _json(handler, status, body):
    data = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output clean
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return None, "body too large"
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, UnicodeDecodeError):
            return None, "invalid JSON"

    def _finish(self, status, body):
        path = urlparse(self.path).path
        STORE.record_request(self.command, path, status)
        _json(self, status, body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            return self._finish(200, {"status": "ok"})
        if path == "/api/content/pages":
            return self._finish(200, {"pages": STORE.list_pages()})
        if path.startswith("/api/content/pages/"):
            slug = path.rsplit("/", 1)[-1]
            page = STORE.get_page(slug)
            if page is None:
                return self._finish(404, {"error": "page not found"})
            return self._finish(200, page)
        if path == "/api/consent":
            visitor_id = parse_qs(parsed.query).get("visitor_id", [None])[0]
            if not visitor_id:
                return self._finish(400, {"error": "visitor_id required"})
            return self._finish(200, STORE.get_consent(visitor_id))
        if path == "/metrics":
            lines = ["# HELP website_requests_total Requests by method, path, status",
                     "# TYPE website_requests_total counter"]
            for (method, p, status), count in sorted(STORE.request_counts.items()):
                lines.append('website_requests_total{method="%s",path="%s",status="%d"} %d'
                             % (method, p, status, count))
            lines.append("website_analytics_events_total %d" % len(STORE.events))
            data = ("\n".join(lines) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return self._finish(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/forms/") and path.endswith("/submissions"):
            form_id = path.split("/")[3]
            payload, err = self._read_json()
            if err:
                return self._finish(400, {"error": err})
            key = self.headers.get("Idempotency-Key")
            if not key:
                return self._finish(400, {"error": "Idempotency-Key header required"})
            status, body = STORE.submit_form(form_id, payload, key)
            return self._finish(status, body)
        if path == "/api/analytics/events":
            payload, err = self._read_json()
            if err:
                return self._finish(400, {"error": err})
            visitor_id = payload.get("visitor_id")
            events = payload.get("events")
            if not visitor_id or not isinstance(events, list):
                return self._finish(400, {"error": "visitor_id and events list required"})
            if len(events) > MAX_EVENTS_PER_BATCH:
                return self._finish(400, {"error": "too many events in one batch"})
            if not STORE.get_consent(visitor_id)["analytics"]:
                return self._finish(403, {"error": "analytics consent not given"})
            bad = [e for e in events if not isinstance(e, dict) or not e.get("name")]
            if bad:
                return self._finish(400, {"error": "every event needs a name"})
            stored = STORE.track_events(visitor_id, events)
            return self._finish(202, {"accepted": len(stored)})
        if path == "/api/consent":
            payload, err = self._read_json()
            if err:
                return self._finish(400, {"error": err})
            visitor_id = payload.get("visitor_id")
            if not visitor_id:
                return self._finish(400, {"error": "visitor_id required"})
            record = STORE.set_consent(visitor_id, payload)
            return self._finish(200, record)
        return self._finish(404, {"error": "not found"})


def create_server(host="127.0.0.1", port=0):
    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    server = create_server(port=8000)
    print("Public website platform API on http://127.0.0.1:8000")
    server.serve_forever()
