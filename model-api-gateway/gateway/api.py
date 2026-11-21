"""HTTP API for the Model API Gateway (stdlib only).

Endpoints:
  POST /v1/models/{model}/completions  — auth, rate limit, route, meter
  GET  /v1/usage                       — per-key usage aggregation
  GET  /v1/billing                     — per-key invoice
  GET  /health                         — liveness
  GET  /metrics                        — Prometheus text
"""

import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .auth import KeyStore
from .metering import Meter, UsageRecord, build_invoice
from .observability import Metrics
from .ratelimit import RateLimiter
from .router import ModelRegistry, Router


def estimate_tokens(text):
    """Rough token estimate (1 token ~ 4 chars) for metering demos."""
    return max(1, len(text or "") // 4)


class Gateway:
    """Wires auth, rate limiting, routing, metering, and metrics together."""

    def __init__(self, key_store=None, registry=None, limiter=None,
                 meter=None, metrics=None):
        self.keys = key_store or KeyStore()
        self.registry = registry or ModelRegistry()
        self.router = Router(self.registry)
        self.limiter = limiter or RateLimiter()
        self.meter = meter or Meter()
        self.metrics = metrics or Metrics()

    def invoke(self, raw_key, model, prompt, max_tokens=128, now=None):
        """Handle one completion request. Returns (status_code, payload dict)."""
        now = time.time() if now is None else now
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        prompt_tokens = estimate_tokens(prompt)
        allowed, wait = self.limiter.check(api_key, prompt_tokens, now=now)
        if not allowed:
            return 429, {"error": "rate_limited",
                         "retry_after_seconds": round(wait, 2)}
        backend, reason = self.router.route(model)
        if backend is None:
            return 404 if reason == "unknown_model" else 503, {"error": reason}
        try:
            # Simulated inference: latency scales with the backend and tokens.
            latency_ms = backend.base_latency_ms + (prompt_tokens + max_tokens) * 0.05
            completion_tokens = min(max_tokens, 24 + len(prompt or "") // 16)
            day = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
            self.meter.record(UsageRecord(api_key.key_id, model, day,
                                          prompt_tokens, completion_tokens, latency_ms))
            self.metrics.observe(model, latency_ms)
            return 200, {
                "model": model,
                "backend": backend.backend_id,
                "completion": "Demo completion for: %s" % (prompt or "")[:80],
                "usage": {"prompt_tokens": prompt_tokens,
                          "completion_tokens": completion_tokens},
                "latency_ms": round(latency_ms, 1),
            }
        finally:
            backend.release()

    def usage_for(self, raw_key, day=None, now=None):
        api_key, reason = self.keys.verify(raw_key, "usage:read", now=now)
        if api_key is None:
            return 401, {"error": reason}
        return 200, {"key_id": api_key.key_id,
                     "usage": self.meter.aggregate(api_key.key_id, day=day)}

    def billing_for(self, raw_key, day=None, now=None):
        api_key, reason = self.keys.verify(raw_key, "billing:read", now=now)
        if api_key is None:
            return 401, {"error": reason}
        usage = self.meter.aggregate(api_key.key_id, day=day)
        return 200, build_invoice(api_key.key_id, usage)


def make_handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep demo output quiet
            pass

        def _send_json(self, status, payload, extra_headers=None):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _bearer_key(self):
            auth = self.headers.get("Authorization", "")
            return auth[len("Bearer "):] if auth.startswith("Bearer ") else ""

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._send_json(200, {"ok": True, "models": self.server.gateway.registry.models()})
            if path == "/metrics":
                body = self.server.gateway.metrics.prometheus_text().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if path == "/v1/usage":
                status, payload = self.server.gateway.usage_for(self._bearer_key())
                return self._send_json(status, payload)
            if path == "/v1/billing":
                status, payload = self.server.gateway.billing_for(self._bearer_key())
                return self._send_json(status, payload)
            return self._send_json(404, {"error": "not_found"})

        def do_POST(self):
            parts = urlparse(self.path).path.strip("/").split("/")
            if len(parts) != 4 or parts[0] != "v1" or parts[1] != "models" or parts[3] != "completions":
                return self._send_json(404, {"error": "not_found"})
            model = parts[2]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, OSError):
                return self._send_json(400, {"error": "invalid_json"})
            status, payload = self.server.gateway.invoke(
                self._bearer_key(), model,
                body.get("prompt", ""), int(body.get("max_tokens", 128)))
            extra = {}
            if status == 429:
                extra["Retry-After"] = str(payload.get("retry_after_seconds", 1))
            return self._send_json(status, payload, extra)

    return Handler


def serve(gateway, host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), make_handler(gateway))
    server.gateway = gateway
    server.serve_forever()
