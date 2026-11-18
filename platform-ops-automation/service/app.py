"""Demo web service for the Platform Ops Automation portfolio project.

Stdlib only (http.server). Tracks request counts, latency samples, and
errors, and exposes them in Prometheus text format on /metrics.

All traffic is synthetic. This is a demo, not a production service.
"""

import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Histogram bucket upper bounds in seconds (Prometheus-style).
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


class Metrics:
    """Thread-safe counters and latency samples for the demo service."""

    def __init__(self):
        self._lock = threading.Lock()
        self.requests_total = 0
        self.errors_total = 0
        self.latencies = []  # seconds, in arrival order

    def record(self, latency_seconds, status_code):
        with self._lock:
            self.requests_total += 1
            self.latencies.append(latency_seconds)
            if status_code >= 500:
                self.errors_total += 1

    def snapshot(self):
        with self._lock:
            return {
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "latencies": list(self.latencies),
            }

    def render_prometheus(self):
        snap = self.snapshot()
        latencies = snap["latencies"]
        lines = [
            "# HELP platform_ops_requests_total Total HTTP requests handled",
            "# TYPE platform_ops_requests_total counter",
            f"platform_ops_requests_total {snap['requests_total']}",
            "# HELP platform_ops_errors_total Total HTTP 5xx responses",
            "# TYPE platform_ops_errors_total counter",
            f"platform_ops_errors_total {snap['errors_total']}",
            "# HELP platform_ops_request_duration_seconds Request latency histogram",
            "# TYPE platform_ops_request_duration_seconds histogram",
        ]
        for bucket in LATENCY_BUCKETS:
            count = sum(1 for value in latencies if value <= bucket)
            lines.append(
                f'platform_ops_request_duration_seconds_bucket{{le="{bucket}"}} {count}'
            )
        lines.append(
            f'platform_ops_request_duration_seconds_bucket{{le="+Inf"}} {len(latencies)}'
        )
        total = sum(latencies)
        lines.append(f"platform_ops_request_duration_seconds_sum {total:.6f}")
        lines.append(f"platform_ops_request_duration_seconds_count {len(latencies)}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()


def simulate_latency():
    """Optional latency knob: env var LATENCY_MS adds a fixed delay plus
    up to 50% jitter. Default is 0 (no artificial delay)."""
    base_ms = float(os.environ.get("LATENCY_MS", "0"))
    if base_ms <= 0:
        return 0.0
    delay = (base_ms * random.uniform(1.0, 1.5)) / 1000.0
    time.sleep(delay)
    return delay


def error_rate():
    """Optional error knob: env var ERROR_RATE (0.0-1.0) makes that fraction
    of / requests return 500. Default is 0."""
    try:
        rate = float(os.environ.get("ERROR_RATE", "0"))
    except ValueError:
        rate = 0.0
    return max(0.0, min(1.0, rate))


DEMO_PAGE = """<!DOCTYPE html>
<html>
<head><title>Platform Ops Automation — Demo</title></head>
<body>
<h1>Platform Ops Automation</h1>
<p>Demo web service for a portfolio project. Synthetic traffic only.</p>
<ul>
  <li><a href="/health">/health</a> — liveness JSON</li>
  <li><a href="/metrics">/metrics</a> — Prometheus text format</li>
</ul>
<p>This is a demo, not a real production platform.</p>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        started = time.monotonic()
        if self.path == "/health":
            status, body, ctype = 200, json.dumps({"status": "ok"}), "application/json"
        elif self.path == "/metrics":
            status, body, ctype = 200, METRICS.render_prometheus(), "text/plain; version=0.0.4"
        elif self.path == "/":
            delay = simulate_latency()
            if random.random() < error_rate():
                status, body, ctype = 500, "simulated error\n", "text/plain"
            else:
                status, body, ctype = 200, DEMO_PAGE, "text/html"
            latency = time.monotonic() - started
            METRICS.record(latency, status)
            self._send(status, body, ctype)
            return
        else:
            status, body, ctype = 404, "not found\n", "text/plain"
        latency = time.monotonic() - started
        METRICS.record(latency, status)
        self._send(status, body, ctype)


def build_server(port, host="0.0.0.0"):
    return ThreadingHTTPServer((host, port), Handler)


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = build_server(port)
    print(f"platform-ops demo service listening on port {port} (synthetic traffic only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
