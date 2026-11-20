"""Environment health checks for a release candidate.

A health check probes one HTTP endpoint and records whether it answered
in time, with the expected status, and with a body that matches the
contract we care about (a JSON object containing required keys).
``check_environment`` runs a list of such probes plus a config check and
returns one result per check, so a failing environment is easy to blame.
"""
import json
import time
import urllib.error
import urllib.request


class HealthCheck:
    """One probe: a name, a URL, the expected status, required JSON keys."""

    def __init__(self, name, url, expected_status=200, required_keys=(),
                 timeout_s=5.0, max_latency_s=2.0):
        self.name = name
        self.url = url
        self.expected_status = expected_status
        self.required_keys = tuple(required_keys)
        self.timeout_s = timeout_s
        self.max_latency_s = max_latency_s

    def run(self):
        """Probe the endpoint. Returns a dict with ok, status, latency, detail."""
        started = time.monotonic()
        try:
            with urllib.request.urlopen(self.url, timeout=self.timeout_s) as resp:
                status = resp.status
                body = resp.read()
        except urllib.error.HTTPError as e:
            # urllib raises for 4xx/5xx; the code and body are still usable,
            # so an expected 404 (e.g. "missing plan") can pass its check.
            status = e.code
            try:
                body = e.read()
            except Exception:
                body = b""
        except Exception as e:  # connection refused, DNS, timeout
            latency = time.monotonic() - started
            return {"name": self.name, "ok": False, "status": None,
                    "latency_s": round(latency, 3),
                    "detail": f"request failed: {type(e).__name__}: {e}"}
        latency = time.monotonic() - started
        if status != self.expected_status:
            return {"name": self.name, "ok": False, "status": status,
                    "latency_s": round(latency, 3),
                    "detail": f"expected HTTP {self.expected_status}, got {status}"}
        if latency > self.max_latency_s:
            return {"name": self.name, "ok": False, "status": status,
                    "latency_s": round(latency, 3),
                    "detail": f"latency {latency:.2f}s exceeds budget "
                              f"{self.max_latency_s:.2f}s"}
        if self.required_keys:
            try:
                payload = json.loads(body)
            except ValueError:
                return {"name": self.name, "ok": False, "status": status,
                        "latency_s": round(latency, 3),
                        "detail": "response body is not valid JSON"}
            if not isinstance(payload, dict):
                return {"name": self.name, "ok": False, "status": status,
                        "latency_s": round(latency, 3),
                        "detail": "response body is not a JSON object"}
            missing = [k for k in self.required_keys if k not in payload]
            if missing:
                return {"name": self.name, "ok": False, "status": status,
                        "latency_s": round(latency, 3),
                        "detail": f"missing required keys: {missing}"}
        return {"name": self.name, "ok": True, "status": status,
                "latency_s": round(latency, 3), "detail": "ok"}


def check_config(config, required_keys):
    """Validate a config mapping has every required key with a non-empty value.

    Returns a result dict in the same shape as ``HealthCheck.run``.
    """
    missing = [k for k in required_keys
               if k not in config or config[k] in (None, "")]
    if missing:
        return {"name": "config", "ok": False, "status": None,
                "latency_s": 0.0,
                "detail": f"missing or empty config keys: {missing}"}
    return {"name": "config", "ok": True, "status": None,
            "latency_s": 0.0, "detail": "ok"}


def check_environment(checks, config=None, config_keys=()):
    """Run every health check (and the config check, if asked for).

    Returns a list of result dicts, one per check, in input order.
    """
    results = [c.run() for c in checks]
    if config_keys:
        results.append(check_config(config or {}, config_keys))
    return results


def all_healthy(results):
    """True when every result in a ``check_environment`` list passed."""
    return bool(results) and all(r["ok"] for r in results)
