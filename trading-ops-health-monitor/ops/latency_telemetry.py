"""Latency telemetry: percentiles and SLO breach detection.

Works on synthetic per-request latency samples (milliseconds).
No real system is measured.
"""


def percentile(samples, pct):
    """Nearest-rank percentile of a non-empty sample list."""
    if not samples:
        raise ValueError("no samples")
    ordered = sorted(samples)
    rank = max(1, int(round(pct / 100.0 * len(ordered))))
    return ordered[min(rank, len(ordered)) - 1]


def latency_summary(samples, slo_ms):
    """Return p50/p95/p99 and whether p95 breaches the SLO."""
    return {
        "count": len(samples),
        "p50_ms": percentile(samples, 50),
        "p95_ms": percentile(samples, 95),
        "p99_ms": percentile(samples, 99),
        "slo_ms": slo_ms,
        "breach": percentile(samples, 95) > slo_ms,
    }


def rolling_breach(samples, window, slo_ms):
    """Flag each rolling window whose p95 breaches the SLO.

    Returns a list of (window_start_index, p95) for breaching windows.
    """
    breaches = []
    for start in range(0, len(samples) - window + 1):
        p95 = percentile(samples[start:start + window], 95)
        if p95 > slo_ms:
            breaches.append((start, p95))
    return breaches
