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
from .marketplace import MarketplaceStore, run_agent_eval, run_serving_eval
from .metering import Meter, UsageRecord, build_invoice
from .observability import Metrics
from .ratelimit import RateLimiter
from .router import ModelRegistry, Router
from .serving import ModelRegistry as ServingRegistry, ModelVersion, Scorer


def estimate_tokens(text):
    """Rough token estimate (1 token ~ 4 chars) for metering demos."""
    return max(1, len(text or "") // 4)


class Gateway:
    """Wires auth, rate limiting, routing, metering, and metrics together."""

    def __init__(self, key_store=None, registry=None, limiter=None,
                 meter=None, metrics=None, serving_registry=None,
                 marketplace=None):
        self.keys = key_store or KeyStore()
        self.registry = registry or ModelRegistry()
        self.router = Router(self.registry)
        self.limiter = limiter or RateLimiter()
        self.meter = meter or Meter()
        self.metrics = metrics or Metrics()
        self.serving_registry = serving_registry or ServingRegistry()
        self.scorer = Scorer(self.serving_registry)
        self.marketplace = marketplace or MarketplaceStore()

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

    # ---- Predictive-model serving -------------------------------------
    def register_model(self, raw_key, spec, now=None):
        """Register a predictive model version (scope: models:invoke)."""
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            version = ModelVersion(spec["name"], spec["version"],
                                   spec.get("framework", "python"),
                                   spec.get("features", []),
                                   spec.get("target", "prediction"),
                                   spec.get("artifact", "demo://%s"),
                                   spec.get("description", ""))
            self.serving_registry.register(version)
        except (KeyError, ValueError) as exc:
            return 400, {"error": "invalid_model_spec", "details": str(exc)}
        return 201, version.to_dict()

    def list_models(self, raw_key, now=None):
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        return 200, {"models": self.serving_registry.models()}

    def predict(self, raw_key, model, features, version=None, now=None):
        """Score one predictive-model request (scope: models:invoke)."""
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        return self.scorer.score(model, features, version=version)

    def serving_metrics(self, raw_key, now=None):
        api_key, reason = self.keys.verify(raw_key, "usage:read", now=now)
        if api_key is None:
            return 401, {"error": reason}
        return 200, {"serving": self.scorer.metrics.summary_all()}

    # ---- Marketplace partner intelligence ------------------------------
    def register_dataset(self, raw_key, spec, now=None):
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            dataset = self.marketplace.register_dataset(
                spec["dataset_id"], spec["name"], spec.get("owner_partner", ""),
                spec.get("columns", []))
        except (KeyError, ValueError) as exc:
            return 400, {"error": "invalid_dataset_spec", "details": str(exc)}
        return 201, dataset.to_dict()

    def ingest_dataset(self, raw_key, dataset_id, rows, now=None):
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            return 200, self.marketplace.ingest(dataset_id, rows)
        except ValueError as exc:
            return 404, {"error": "unknown_dataset", "details": str(exc)}

    def define_metric(self, raw_key, spec, now=None):
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            metric = self.marketplace.define_metric(
                spec["name"], spec["dataset_id"], spec["column"],
                spec["aggregation"], spec.get("description", ""))
        except (KeyError, ValueError) as exc:
            return 400, {"error": "invalid_metric_spec", "details": str(exc)}
        return 201, metric.to_dict()

    def query_metric(self, raw_key, name, filters=None, now=None):
        api_key, reason = self.keys.verify(raw_key, "usage:read", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            return 200, self.marketplace.query_metric(name, filters)
        except ValueError as exc:
            return 404, {"error": "unknown_metric", "details": str(exc)}

    def run_serving_eval(self, raw_key, spec, now=None):
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            return 200, run_serving_eval(
                self.marketplace, self.scorer, spec["model"],
                spec.get("cases", []), spec.get("min_pass_rate", 0.8))
        except KeyError as exc:
            return 400, {"error": "invalid_eval_spec", "details": str(exc)}

    def get_serving_eval(self, raw_key, run_id, now=None):
        api_key, reason = self.keys.verify(raw_key, "usage:read", now=now)
        if api_key is None:
            return 401, {"error": reason}
        run = self.marketplace.serving_eval_runs.get(run_id)
        if run is None:
            return 404, {"error": "unknown_eval_run", "run_id": run_id}
        return 200, run.to_dict()

    def run_agent_eval(self, raw_key, spec, now=None):
        api_key, reason = self.keys.verify(raw_key, "models:invoke", now=now)
        if api_key is None:
            return 401, {"error": reason}
        try:
            return 200, run_agent_eval(
                self.marketplace, spec.get("agent", "demo-agent"),
                spec.get("cases", []), spec.get("min_pass_rate", 0.8))
        except KeyError as exc:
            return 400, {"error": "invalid_eval_spec", "details": str(exc)}

    def get_agent_eval(self, raw_key, run_id, now=None):
        api_key, reason = self.keys.verify(raw_key, "usage:read", now=now)
        if api_key is None:
            return 401, {"error": reason}
        run = self.marketplace.agent_eval_runs.get(run_id)
        if run is None:
            return 404, {"error": "unknown_eval_run", "run_id": run_id}
        return 200, run.to_dict()


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
            if path == "/v1/serving/models":
                status, payload = self.server.gateway.list_models(self._bearer_key())
                return self._send_json(status, payload)
            if path == "/v1/serving/metrics":
                status, payload = self.server.gateway.serving_metrics(self._bearer_key())
                return self._send_json(status, payload)
            if len(path.strip("/").split("/")) == 5 and path.startswith("/v1/marketplace/evals/serving/"):
                run_id = path.strip("/").split("/")[4]
                status, payload = self.server.gateway.get_serving_eval(self._bearer_key(), run_id)
                return self._send_json(status, payload)
            if len(path.strip("/").split("/")) == 5 and path.startswith("/v1/marketplace/evals/agents/"):
                run_id = path.strip("/").split("/")[4]
                status, payload = self.server.gateway.get_agent_eval(self._bearer_key(), run_id)
                return self._send_json(status, payload)
            return self._send_json(404, {"error": "not_found"})

        def _read_json_body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length) or b"{}"), None
            except (ValueError, OSError):
                return None, self._send_json(400, {"error": "invalid_json"})

        def do_POST(self):
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts == ["v1", "marketplace", "datasets"]:
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.register_dataset(
                    self._bearer_key(), body)
                return self._send_json(status, payload)
            if len(parts) == 5 and parts[:3] == ["v1", "marketplace", "datasets"] and parts[4] == "ingest":
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.ingest_dataset(
                    self._bearer_key(), parts[3], body.get("rows", []))
                return self._send_json(status, payload)
            if parts == ["v1", "marketplace", "semantic", "metrics"]:
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.define_metric(
                    self._bearer_key(), body)
                return self._send_json(status, payload)
            if parts == ["v1", "marketplace", "semantic", "query"]:
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.query_metric(
                    self._bearer_key(), body.get("metric", ""),
                    body.get("filters"))
                return self._send_json(status, payload)
            if parts == ["v1", "marketplace", "evals", "serving"]:
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.run_serving_eval(
                    self._bearer_key(), body)
                return self._send_json(status, payload)
            if parts == ["v1", "marketplace", "evals", "agents"]:
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.run_agent_eval(
                    self._bearer_key(), body)
                return self._send_json(status, payload)
            if parts == ["v1", "serving", "models"]:
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.register_model(
                    self._bearer_key(), body)
                return self._send_json(status, payload)
            if len(parts) == 5 and parts[:3] == ["v1", "serving", "models"] and parts[4] == "predict":
                body, err = self._read_json_body()
                if err is not None:
                    return err
                status, payload = self.server.gateway.predict(
                    self._bearer_key(), parts[3],
                    body.get("features", {}), body.get("version"))
                return self._send_json(status, payload)
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
