"""The running prototype service: JSON API + a frontend page per prototype.

One small stdlib HTTP service serves the whole stack a prototype needs:
a JSON API (list prototypes, submit feedback, read metrics) and a plain
HTML page per prototype that a real user can open in a browser, try the
prototype, and leave feedback on. No framework, no database — state
lives in the idea/prototype/feedback stores passed in.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .pipeline import FeedbackPipeline


def make_handler(ideas, prototypes, pipeline):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep demo output clean
            pass

        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload, indent=2))

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/health":
                return self._json(200, {"status": "ok"})
            if path == "/api/prototypes":
                return self._json(200, [
                    {"slug": p.slug, "idea_slug": p.idea_slug, "name": p.name,
                     "status": p.status, "frontend_page": p.frontend_page,
                     "build_minutes": p.build_minutes}
                    for p in prototypes.list()])
            if path.startswith("/api/prototypes/") and path.endswith("/metrics"):
                slug = path[len("/api/prototypes/"):-len("/metrics")].strip("/")
                metrics = pipeline.metrics(slug)
                if metrics is None:
                    return self._json(404, {"error": f"no feedback yet for {slug!r}"})
                return self._json(200, metrics)
            if path.startswith("/prototypes/"):
                idea_slug = path[len("/prototypes/"):].strip("/")
                proto = prototypes.get(idea_slug)
                if proto is None:
                    return self._send(404, "prototype not found", "text/plain")
                idea = ideas.get(idea_slug)
                return self._send(200, render_page(proto, idea), "text/html; charset=utf-8")
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"error": "body must be valid JSON"})
            if path == "/api/feedback":
                if not isinstance(payload, dict):
                    return self._json(400, {"error": "body must be a JSON object"})
                result = pipeline.ingest(payload)
                if result == "accepted":
                    return self._json(201, {"result": "accepted"})
                if result == "duplicate":
                    return self._json(200, {"result": "duplicate"})
                return self._json(422, {"result": "quarantined",
                                        "reason": pipeline.quarantined[-1].reason})
            return self._json(404, {"error": "not found"})

    return Handler


def render_page(proto, idea):
    """The frontend page for one prototype: what it is, what to try, feedback form."""
    problem = idea.problem if idea else ""
    user = idea.target_user if idea else ""
    metric = idea.success_metric if idea else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{proto.name}</title></head>
<body>
<h1>{proto.name}</h1>
<p><strong>Prototype:</strong> {proto.slug} &mdash; status {proto.status}, built in {proto.build_minutes} minutes.</p>
<p><strong>Problem:</strong> {problem}</p>
<p><strong>For:</strong> {user}</p>
<p><strong>Success looks like:</strong> {metric}</p>
<h2>Try it</h2>
<p>API: <code>GET /api/prototypes</code> &middot; <code>POST /api/feedback</code> with
<code>{{"user_id", "prototype_slug", "rating" (1-5), "comment", "day"}}</code>.</p>
<h2>Leave feedback</h2>
<form method="post" action="/api/feedback">
<label>Rating (1-5): <input name="rating" type="number" min="1" max="5"></label>
<input type="hidden" name="prototype_slug" value="{proto.slug}">
<button type="submit">Send feedback</button>
</form>
<p><em>Prototype build — synthetic demo data only.</em></p>
</body></html>
"""


def serve(ideas, prototypes, pipeline, host="127.0.0.1", port=0):
    """Start the service on an ephemeral port by default; returns the server."""
    handler = make_handler(ideas, prototypes, pipeline)
    server = ThreadingHTTPServer((host, port), handler)
    return server
