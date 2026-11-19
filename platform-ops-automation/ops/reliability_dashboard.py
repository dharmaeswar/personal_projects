"""Operational health summary for the Platform Ops Automation demo project.

Aggregates synthetic per-request health signals into an operational health
summary: availability, error rate, p95 latency, error-budget burn, and
alert evaluation. The alert-rule shape mirrors Azure Monitor-style alert
rules (threshold on error rate / availability over a window) as a study;
nothing here claims production Azure experience.

Signal format (dict):
    {"service": "teller", "ok": True, "latency": 0.042}
"""

import math
import random
from collections import defaultdict


def summarize(signals, slo_availability=99.9):
    """Summarize health signals.

    Returns a dict with total requests, errors, availability %, error rate,
    p95 latency, error-budget remaining (percentage points of the SLO
    budget not yet consumed), and a per-service breakdown.
    """
    total = len(signals)
    errors = sum(1 for s in signals if not s["ok"])
    latencies = sorted(s["latency"] for s in signals)
    availability = (total - errors) / total * 100.0 if total else 100.0
    error_rate = errors / total if total else 0.0
    if latencies:
        rank = max(1, min(len(latencies), math.ceil(0.95 * len(latencies))))
        p95 = latencies[rank - 1]
    else:
        p95 = None
    allowed_error = 100.0 - slo_availability
    budget_remaining = allowed_error - error_rate * 100.0
    by_service = {}
    grouped = defaultdict(list)
    for s in signals:
        grouped[s["service"]].append(s)
    for service, items in sorted(grouped.items()):
        svc_errors = sum(1 for s in items if not s["ok"])
        by_service[service] = {
            "total": len(items),
            "errors": svc_errors,
            "availability": (len(items) - svc_errors) / len(items) * 100.0
            if items
            else 100.0,
        }
    return {
        "total": total,
        "errors": errors,
        "availability": availability,
        "error_rate": error_rate,
        "p95_latency": p95,
        "error_budget_remaining": budget_remaining,
        "by_service": by_service,
    }


def evaluate_alerts(summary, error_rate_threshold=0.05, p95_threshold=0.5):
    """Evaluate alert rules over a summary.

    Fires an alert when availability is below the SLO (error budget
    exhausted), when the error rate exceeds `error_rate_threshold`, or
    when p95 latency exceeds `p95_threshold` seconds. Returns a list of
    alert dicts with severity and message.
    """
    alerts = []
    if summary["error_budget_remaining"] < 0:
        alerts.append(
            {
                "rule": "availability-below-slo",
                "severity": "critical",
                "message": (
                    f"availability {summary['availability']:.2f}% is below "
                    "the SLO; error budget exhausted"
                ),
            }
        )
    if summary["error_rate"] > error_rate_threshold:
        alerts.append(
            {
                "rule": "error-rate-high",
                "severity": "warning",
                "message": (
                    f"error rate {summary['error_rate']:.1%} exceeds "
                    f"threshold {error_rate_threshold:.1%}"
                ),
            }
        )
    p95 = summary["p95_latency"]
    if p95 is not None and p95 > p95_threshold:
        alerts.append(
            {
                "rule": "latency-p95-high",
                "severity": "warning",
                "message": (
                    f"p95 latency {p95:.3f}s exceeds threshold "
                    f"{p95_threshold:.3f}s"
                ),
            }
        )
    return alerts


def generate_synthetic_signals(seed=7, services=("teller", "account-opening")):
    """Generate synthetic health signals: mostly healthy, one service with
    an elevated error rate. Returns a list of signal dicts."""
    rng = random.Random(seed)
    signals = []
    for service in services:
        for _ in range(400):
            is_error = service == "teller" and rng.random() < 0.08
            latency = round(
                rng.uniform(0.3, 0.9) if is_error else rng.uniform(0.01, 0.15), 3
            )
            signals.append(
                {"service": service, "ok": not is_error, "latency": latency}
            )
    return signals


def main():
    signals = generate_synthetic_signals()
    summary = summarize(signals)
    print(f"total={summary['total']} errors={summary['errors']}")
    print(f"availability={summary['availability']:.2f}%")
    print(f"error rate={summary['error_rate']:.1%}")
    print(f"p95 latency={summary['p95_latency']:.3f}s")
    print(f"error budget remaining={summary['error_budget_remaining']:.2f} pts")
    for service, stats in summary["by_service"].items():
        print(
            f"{service}: total={stats['total']} errors={stats['errors']} "
            f"availability={stats['availability']:.2f}%"
        )
    for alert in evaluate_alerts(summary):
        print(f"ALERT [{alert['severity']}] {alert['rule']}: {alert['message']}")
    if not evaluate_alerts(summary):
        print("no alerts fired")


if __name__ == "__main__":
    main()
