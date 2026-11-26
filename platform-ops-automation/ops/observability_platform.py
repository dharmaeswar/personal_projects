"""Observability platform: trace/log/metric correlation, anomaly detection,
and root-cause ranking for the Platform Ops Automation demo project.

Added Nov 26, 2026, for a Gusto Site Reliability Engineer application.
Gusto's posting asks for an observability platform covering distributed
logging, metrics and tracing; anomaly detection and faster root-cause
analysis; dashboards and interactive debugging tools; and intelligent
alerting, diagnostics and incident response.

What this module does, on synthetic input only:

- Correlates distributed traces, logs and metrics by trace id, so one
  incident view shows the failing span, its logs, and the metric series
  around it.
- Detects anomalies with a rolling statistical baseline (mean and
  standard deviation over a trailing window, z-score flag). This is
  plain statistics, not an AI model; no claim of AI-native detection
  is made.
- Ranks likely root causes for an incident window by comparing each
  service/operation's error rate and latency against its own baseline.
- Routes alerts by severity and blast radius (page on-call, open a
  ticket, or log only).

All data is synthetic. No real observability tool (Datadog, Sentry,
Splunk, OpenTelemetry collector or Prometheus server) is contacted,
and no production observability-platform experience is claimed.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict


# ---------------------------------------------------------------------------
# Trace / log / metric correlation
# ---------------------------------------------------------------------------

def correlate_incident(spans, logs, metrics):
    """Join spans, logs and metrics for one incident into a single view.

    ``spans``: list of dicts with ``trace_id``, ``span_id``, ``service``,
    ``operation``, ``duration_ms``, ``status`` (``"ok"`` / ``"error"``)
    and ``start_ms``. ``logs``: list of dicts with ``trace_id``,
    ``timestamp_ms``, ``level`` and ``message``. ``metrics``: list of
    dicts with ``timestamp_ms``, ``name`` and ``value``.

    Returns a dict with the trace ids involved, the error spans, the
    matching log lines, the metric samples inside the incident window,
    and the slowest span (the first place to look).
    """
    trace_ids = sorted({span["trace_id"] for span in spans})
    error_spans = [s for s in spans if s["status"] == "error"]
    by_trace_logs = defaultdict(list)
    for log in logs:
        by_trace_logs[log["trace_id"]].append(log)
    incident_logs = [log for tid in trace_ids for log in by_trace_logs.get(tid, [])]
    incident_logs.sort(key=lambda log: log["timestamp_ms"])
    if spans:
        start = min(span["start_ms"] for span in spans)
        end = max(span["start_ms"] + span["duration_ms"] for span in spans)
    else:
        start = end = 0
    window_metrics = [
        m for m in metrics if start <= m["timestamp_ms"] <= end
    ]
    slowest = max(spans, key=lambda s: s["duration_ms"]) if spans else None
    return {
        "trace_ids": trace_ids,
        "error_spans": error_spans,
        "error_count": len(error_spans),
        "logs": incident_logs,
        "log_count": len(incident_logs),
        "metrics_in_window": window_metrics,
        "window_ms": (start, end),
        "slowest_span": slowest,
    }


def trace_timeline(spans):
    """Return spans ordered by start time with depth from parent links.

    Each span may carry ``parent_span_id`` (None for a root span).
    Returns a list of ``(depth, span)`` tuples in start-time order.
    """
    by_id = {span["span_id"]: span for span in spans}

    def depth(span, seen=None):
        seen = seen or set()
        parent = span.get("parent_span_id")
        if not parent or parent not in by_id or parent in seen:
            return 0
        seen.add(parent)
        return 1 + depth(by_id[parent], seen)

    ordered = sorted(spans, key=lambda s: s["start_ms"])
    return [(depth(span), span) for span in ordered]


# ---------------------------------------------------------------------------
# Statistical anomaly detection (rolling baseline, z-score)
# ---------------------------------------------------------------------------

def detect_anomalies(samples, window=20, z_threshold=3.0, min_baseline=10):
    """Flag anomalous points in a per-minute metric series.

    ``samples``: list of dicts ``{"minute": int, "value": float}`` in
    time order. For each point, the baseline is the mean and standard
    deviation of the previous ``window`` points; a point is anomalous
    when its z-score is at or above ``z_threshold``. Points before
    ``min_baseline`` samples are never flagged. Returns a list of
    dicts with ``minute``, ``value``, ``baseline_mean``,
    ``baseline_std`` and ``z_score``.
    """
    anomalies = []
    values = [s["value"] for s in samples]
    for i, sample in enumerate(samples):
        if i < min_baseline:
            continue
        baseline = values[max(0, i - window):i]
        mean = statistics.fmean(baseline)
        std = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
        if std == 0.0:
            z = 0.0 if sample["value"] == mean else float("inf")
        else:
            z = (sample["value"] - mean) / std
        if abs(z) >= z_threshold:
            anomalies.append({
                "minute": sample["minute"],
                "value": sample["value"],
                "baseline_mean": round(mean, 4),
                "baseline_std": round(std, 4),
                "z_score": round(z, 2),
            })
    return anomalies


def summarize_series(samples):
    """Basic stats for a metric series: count, mean, std, min, max, p95."""
    values = sorted(s["value"] for s in samples)
    if not values:
        return {"count": 0, "mean": 0.0, "std": 0.0,
                "min": 0.0, "max": 0.0, "p95": 0.0}
    n = len(values)
    p95_index = min(n - 1, math.ceil(0.95 * n) - 1)
    return {
        "count": n,
        "mean": round(statistics.fmean(values), 4),
        "std": round(statistics.pstdev(values), 4) if n > 1 else 0.0,
        "min": values[0],
        "max": values[-1],
        "p95": values[p95_index],
    }


# ---------------------------------------------------------------------------
# Root-cause ranking
# ---------------------------------------------------------------------------

def rank_root_causes(baseline, incident):
    """Rank services/operations by how much worse they got in the incident.

    ``baseline`` and ``incident`` are lists of per-request dicts with
    ``service``, ``operation``, ``ok`` (bool) and ``latency_ms``.
    Each group is scored by its error-rate lift (incident error rate
    minus baseline error rate) plus its latency lift in units of the
    baseline p95, so a group that both errors more and slows down
    ranks first. Returns groups sorted by score, highest first, each
    with ``service``, ``operation``, ``baseline_error_rate``,
    ``incident_error_rate``, ``latency_lift`` and ``score``.
    """
    def group_stats(rows):
        groups = defaultdict(lambda: {"total": 0, "errors": 0, "latencies": []})
        for row in rows:
            key = (row["service"], row["operation"])
            groups[key]["total"] += 1
            if not row["ok"]:
                groups[key]["errors"] += 1
            groups[key]["latencies"].append(row["latency_ms"])
        out = {}
        for key, g in groups.items():
            lat = sorted(g["latencies"])
            p95 = lat[min(len(lat) - 1, math.ceil(0.95 * len(lat)) - 1)]
            out[key] = {
                "error_rate": g["errors"] / g["total"] if g["total"] else 0.0,
                "p95_latency": p95,
                "total": g["total"],
            }
        return out

    base = group_stats(baseline)
    current = group_stats(incident)
    ranked = []
    for key, cur in current.items():
        b = base.get(key, {"error_rate": 0.0, "p95_latency": 1.0, "total": 0})
        error_lift = cur["error_rate"] - b["error_rate"]
        latency_lift = (cur["p95_latency"] - b["p95_latency"]) / max(b["p95_latency"], 1.0)
        score = round(error_lift + max(latency_lift, 0.0), 4)
        ranked.append({
            "service": key[0],
            "operation": key[1],
            "baseline_error_rate": round(b["error_rate"], 4),
            "incident_error_rate": round(cur["error_rate"], 4),
            "latency_lift": round(latency_lift, 4),
            "score": score,
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Intelligent alert routing
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def route_alert(anomaly, error_rate, services_affected, on_call="primary"):
    """Decide what happens with one detected anomaly.

    ``anomaly``: dict from :func:`detect_anomalies`. ``error_rate``:
    current error rate as a fraction. ``services_affected``: how many
    services show the anomaly. Returns a dict with ``severity``,
    ``action`` (``page``, ``ticket`` or ``log``), ``channel`` and a
    short ``reason``.
    """
    z = abs(anomaly["z_score"])
    if error_rate >= 0.05 or services_affected >= 3 or z >= 6.0:
        severity, action, channel = "critical", "page", f"on-call:{on_call}"
        reason = "high error rate, wide blast radius, or extreme deviation"
    elif error_rate >= 0.01 or services_affected >= 2 or z >= 4.0:
        severity, action, channel = "warning", "ticket", "reliability-queue"
        reason = "elevated error rate or multi-service deviation"
    else:
        severity, action, channel = "info", "log", "observability-log"
        reason = "isolated deviation below paging thresholds"
    return {
        "minute": anomaly["minute"],
        "severity": severity,
        "action": action,
        "channel": channel,
        "reason": reason,
    }


def dashboard_summary(service_signals):
    """Per-service health rollup for a dashboard view.

    ``service_signals``: list of dicts with ``service``, ``ok`` and
    ``latency_ms``. Returns one row per service with availability,
    error rate and p95 latency, sorted worst availability first.
    """
    groups = defaultdict(list)
    for signal in service_signals:
        groups[signal["service"]].append(signal)
    rows = []
    for service, signals in groups.items():
        total = len(signals)
        errors = sum(1 for s in signals if not s["ok"])
        lat = sorted(s["latency_ms"] for s in signals)
        p95 = lat[min(total - 1, math.ceil(0.95 * total) - 1)]
        rows.append({
            "service": service,
            "total": total,
            "availability": round(100.0 * (total - errors) / total, 2),
            "error_rate": round(errors / total, 4),
            "p95_latency_ms": p95,
        })
    rows.sort(key=lambda r: r["availability"])
    return rows
