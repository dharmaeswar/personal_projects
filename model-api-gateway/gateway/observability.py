"""Observability: latency histograms, error counts, SLO checks, alerts.

Per-model request latencies are kept in bounded lists; p50/p95 are
computed from them. An SLO is a p95 latency budget plus an error-rate
budget; `evaluate_slo` reports whether each budget is met and which
alert rules fired.
"""

import threading

DEFAULT_P95_BUDGET_MS = 500.0
DEFAULT_ERROR_BUDGET = 0.01  # 1% of requests may error


def percentile(sorted_values, pct):
    """Nearest-rank percentile of an already-sorted list (None when empty)."""
    if not sorted_values:
        return None
    index = int(-(-pct * len(sorted_values) // 100))  # ceil(pct/100 * n)
    index = max(1, min(index, len(sorted_values)))
    return sorted_values[index - 1]


class Metrics:
    def __init__(self, max_samples=10_000):
        self.max_samples = max_samples
        self._latencies = {}  # model -> [ms]
        self._errors = {}     # model -> count
        self._total = {}      # model -> count
        self._lock = threading.Lock()

    def observe(self, model, latency_ms, error=False):
        with self._lock:
            samples = self._latencies.setdefault(model, [])
            samples.append(float(latency_ms))
            if len(samples) > self.max_samples:
                samples.pop(0)
            self._total[model] = self._total.get(model, 0) + 1
            if error:
                self._errors[model] = self._errors.get(model, 0) + 1

    def summary(self, model):
        """Return {requests, errors, error_rate, p50_ms, p95_ms} (None stats when empty)."""
        with self._lock:
            samples = sorted(self._latencies.get(model, []))
            total = self._total.get(model, 0)
            errors = self._errors.get(model, 0)
        return {
            "requests": total,
            "errors": errors,
            "error_rate": (errors / total) if total else 0.0,
            "p50_ms": percentile(samples, 50),
            "p95_ms": percentile(samples, 95),
        }

    def evaluate_slo(self, model, p95_budget_ms=DEFAULT_P95_BUDGET_MS,
                     error_budget=DEFAULT_ERROR_BUDGET):
        """Return {ok, alerts[]} for one model's SLO budgets."""
        stats = self.summary(model)
        alerts = []
        if stats["requests"] == 0:
            return {"ok": True, "alerts": [], "stats": stats}
        if stats["p95_ms"] is not None and stats["p95_ms"] > p95_budget_ms:
            alerts.append("p95_latency_breach: %.1fms > %.1fms budget"
                          % (stats["p95_ms"], p95_budget_ms))
        if stats["error_rate"] > error_budget:
            alerts.append("error_rate_breach: %.2f%% > %.2f%% budget"
                          % (stats["error_rate"] * 100, error_budget * 100))
        return {"ok": not alerts, "alerts": alerts, "stats": stats}

    def prometheus_text(self):
        """Minimal Prometheus exposition format for latencies and errors."""
        lines = []
        with self._lock:
            models = sorted(self._total)
        for model in models:
            stats = self.summary(model)
            lines.append('gateway_requests_total{model="%s"} %d' % (model, stats["requests"]))
            lines.append('gateway_errors_total{model="%s"} %d' % (model, stats["errors"]))
            if stats["p95_ms"] is not None:
                lines.append('gateway_latency_p95_ms{model="%s"} %.1f' % (model, stats["p95_ms"]))
        return "\n".join(lines) + ("\n" if lines else "")
