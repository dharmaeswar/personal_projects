"""Monitoring, alerting, and log analysis for high-volume services.

Covers the JD's monitoring / alerting / debugging need: counters and
latency samples per operation, percentile computation, threshold alert
rules (error rate, p95 latency, queue depth), and structured log analysis
(error counts by code, slowest operations) for debugging production issues.
"""

import re
import statistics
from collections import Counter, defaultdict


class Metrics:
    """Per-operation counters and latency samples, with percentile reads."""

    def __init__(self):
        self.counters: Counter = Counter()
        self.latencies: dict[str, list[float]] = defaultdict(list)

    def record(self, operation: str, latency_ms: float, ok: bool = True) -> None:
        self.counters[f"{operation}.total"] += 1
        if not ok:
            self.counters[f"{operation}.errors"] += 1
        self.latencies[operation].append(latency_ms)

    def error_rate(self, operation: str) -> float:
        total = self.counters[f"{operation}.total"]
        if total == 0:
            return 0.0
        return self.counters[f"{operation}.errors"] / total

    def percentile(self, operation: str, pct: float) -> float | None:
        samples = sorted(self.latencies.get(operation, []))
        if not samples:
            return None
        idx = min(len(samples) - 1, max(0, int(pct / 100 * len(samples))))
        return samples[idx]

    def summary(self) -> dict:
        out = {}
        for operation in self.latencies:
            out[operation] = {
                "total": self.counters[f"{operation}.total"],
                "errors": self.counters[f"{operation}.errors"],
                "error_rate": round(self.error_rate(operation), 4),
                "p50_ms": self.percentile(operation, 50),
                "p95_ms": self.percentile(operation, 95),
            }
        return out


class AlertRule:
    """One threshold rule: fires when a measured value crosses the limit."""

    def __init__(self, name: str, metric: str, threshold: float, comparison: str = ">"):
        self.name = name
        self.metric = metric
        self.threshold = threshold
        self.comparison = comparison

    def check(self, value: float) -> str | None:
        fired = value > self.threshold if self.comparison == ">" else value < self.threshold
        return f"ALERT {self.name}: {self.metric}={value} crossed {self.threshold}" if fired else None


def evaluate_alerts(metrics: Metrics, rules: list[AlertRule], extra: dict[str, float] | None = None) -> list[str]:
    """Evaluate alert rules against live metrics plus caller-supplied values."""
    values: dict[str, float] = dict(extra or {})
    for operation in metrics.latencies:
        values[f"{operation}.error_rate"] = metrics.error_rate(operation)
        p95 = metrics.percentile(operation, 95)
        if p95 is not None:
            values[f"{operation}.p95_ms"] = p95
    fired = []
    for rule in rules:
        if rule.metric in values:
            alert = rule.check(values[rule.metric])
            if alert:
                fired.append(alert)
    return fired


LOG_LINE = re.compile(
    r"^(?P<ts>\S+) (?P<level>INFO|WARN|ERROR) (?P<op>\S+) (?P<ms>\d+(?:\.\d+)?)ms"
    r"(?: code=(?P<code>\S+))?(?: (?P<msg>.*))?$"
)


def analyze_logs(lines: list[str]) -> dict:
    """Summarize structured log lines: error counts by code, slowest operations."""
    errors_by_code: Counter = Counter()
    slowest: dict[str, float] = {}
    total = 0
    malformed = 0
    for line in lines:
        match = LOG_LINE.match(line.strip())
        if not match:
            malformed += 1
            continue
        total += 1
        op, ms = match.group("op"), float(match.group("ms"))
        slowest[op] = max(slowest.get(op, 0.0), ms)
        if match.group("level") == "ERROR":
            errors_by_code[match.group("code") or "UNKNOWN"] += 1
    return {
        "total_lines": total,
        "malformed_lines": malformed,
        "errors_by_code": dict(errors_by_code),
        "slowest_ms_by_operation": slowest,
    }
