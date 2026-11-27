"""KRI / KPI evaluation: threshold status, trend detection (emerging risks),
and dashboard rows for Power BI-style reporting.
"""

from __future__ import annotations


def kri_status(kri):
    """Current reading vs warning/breach thresholds. Returns OK / WARNING / BREACH."""
    current = kri.history[-1]
    if kri.higher_is_worse:
        if current >= kri.breach:
            return "BREACH"
        if current >= kri.warning:
            return "WARNING"
        return "OK"
    if current <= kri.breach:
        return "BREACH"
    if current <= kri.warning:
        return "WARNING"
    return "OK"


def _worsening(a, b, higher_is_worse):
    return b > a if higher_is_worse else b < a


def is_emerging_risk(kri, periods=3):
    """True when the last `periods` readings worsen monotonically — an emerging risk."""
    hist = kri.history
    if len(hist) < periods:
        return False
    tail = hist[-periods:]
    return all(_worsening(tail[i], tail[i + 1], kri.higher_is_worse) for i in range(periods - 1))


def kri_dashboard(kris):
    """One dashboard row per KRI: current value, status, trend, emerging-risk flag."""
    rows = []
    for k in kris:
        rows.append({
            "kri_id": k.kri_id,
            "name": k.name,
            "unit": k.unit,
            "current": k.history[-1],
            "warning": k.warning,
            "breach": k.breach,
            "status": kri_status(k),
            "emerging_risk": is_emerging_risk(k),
            "history": " -> ".join(str(v) for v in k.history),
        })
    return rows


def breached_kris(kris):
    return [k for k in kris if kri_status(k) == "BREACH"]


def emerging_kris(kris):
    return [k for k in kris if is_emerging_risk(k)]
