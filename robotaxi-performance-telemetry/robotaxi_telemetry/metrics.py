"""Fleet performance metrics: KPIs a robotaxi readiness review needs.

Metrics are computed from trip rows (see data.to_rows): intervention
rate per 1,000 miles, mission completion, mean recovery time, remote
assistance rate, mean pickup delay, and vehicle availability proxy
(share of trips with no intervention and no recovery time).
"""
from __future__ import annotations

from .data import INTERVENTION_TYPES


def _sum(rows, key):
    return sum(r[key] for r in rows)


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def intervention_rate_per_1k_miles(rows) -> float:
    miles = _sum(rows, "miles")
    if miles == 0:
        return 0.0
    return 1000.0 * _sum(rows, "interventions_total") / miles


def intervention_rate_by_type(rows) -> dict:
    miles = _sum(rows, "miles")
    if miles == 0:
        return {k: 0.0 for k in INTERVENTION_TYPES}
    return {
        k: 1000.0 * _sum(rows, f"interventions_{k}") / miles
        for k in INTERVENTION_TYPES
    }


def mission_completion_rate(rows) -> float:
    if not rows:
        return 0.0
    return _sum(rows, "mission_completed") / len(rows)


def mean_recovery_min(rows) -> float:
    rec = [r["recovery_min"] for r in rows if r["interventions_total"] > 0]
    return _mean(rec)


def remote_assistance_rate(rows) -> float:
    if not rows:
        return 0.0
    return _sum(rows, "remote_assistance") / len(rows)


def mean_pickup_delay_min(rows) -> float:
    return _mean([r["pickup_delay_min"] for r in rows])


def availability_proxy(rows) -> float:
    """Share of trips needing neither an intervention nor recovery."""
    if not rows:
        return 0.0
    ok = sum(
        1
        for r in rows
        if r["interventions_total"] == 0 and r["recovery_min"] == 0.0
    )
    return ok / len(rows)


def kpi_summary(rows) -> dict:
    return {
        "trips": len(rows),
        "miles": round(_sum(rows, "miles"), 1),
        "interventions_per_1k_miles": round(intervention_rate_per_1k_miles(rows), 3),
        "by_type_per_1k_miles": {
            k: round(v, 3) for k, v in intervention_rate_by_type(rows).items()
        },
        "mission_completion_rate": round(mission_completion_rate(rows), 4),
        "mean_recovery_min": round(mean_recovery_min(rows), 2),
        "remote_assistance_rate": round(remote_assistance_rate(rows), 4),
        "mean_pickup_delay_min": round(mean_pickup_delay_min(rows), 2),
        "availability_proxy": round(availability_proxy(rows), 4),
    }


def kpi_by_release(rows) -> dict:
    out = {}
    for release in sorted({r["release"] for r in rows}):
        out[release] = kpi_summary([r for r in rows if r["release"] == release])
    return out


def kpi_by_road(rows) -> dict:
    out = {}
    for road in sorted({r["road_type"] for r in rows}):
        out[road] = kpi_summary([r for r in rows if r["road_type"] == road])
    return out
