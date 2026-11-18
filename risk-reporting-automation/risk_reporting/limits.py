"""Limit utilisation and breach flags.

Utilisation = aggregated exposure / limit for a (desk, risk_type) group.
Status bands: BREACH at >= 100%, WARNING at >= 90%, OK below 90%.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import Limit, Position

BREACH_THRESHOLD = 1.00
WARNING_THRESHOLD = 0.90


@dataclass(frozen=True)
class LimitResult:
    desk: str
    risk_type: str
    exposure_usd: float
    limit_usd: float
    utilisation: float
    status: str  # OK | WARNING | BREACH


def utilisation(exposure_usd: float, limit_usd: float) -> float:
    if limit_usd <= 0:
        raise ValueError("limit must be positive")
    return exposure_usd / limit_usd


def status_for(util: float) -> str:
    if util >= BREACH_THRESHOLD:
        return "BREACH"
    if util >= WARNING_THRESHOLD:
        return "WARNING"
    return "OK"


def validate_position(pos: Position) -> str | None:
    """Return a validation error message, or None if the row is valid."""
    if pos.exposure_usd < 0:
        return f"negative exposure {pos.exposure_usd}"
    if pos.notional_usd < 0:
        return f"negative notional {pos.notional_usd}"
    return None


def aggregate_exposures(
    positions: list[Position], limits: list[Limit]
) -> tuple[list[LimitResult], list[dict]]:
    """Aggregate valid positions per (desk, risk_type) and check limits.

    Returns (limit results, exceptions). Positions with no matching limit
    or failing validation go to exceptions and are excluded from the
    aggregates, so bad source rows can never inflate or hide a breach.
    """
    limit_map = {(lim.desk, lim.risk_type): lim for lim in limits}
    totals: dict[tuple[str, str], float] = {}
    exceptions: list[dict] = []
    for pos in positions:
        error = validate_position(pos)
        if error is not None:
            exceptions.append(
                {"trade_id": pos.trade_id, "desk": pos.desk,
                 "risk_type": pos.risk_type, "reason": error,
                 "severity": "HIGH"}
            )
            continue
        key = (pos.desk, pos.risk_type)
        if key not in limit_map:
            exceptions.append(
                {"trade_id": pos.trade_id, "desk": pos.desk,
                 "risk_type": pos.risk_type,
                 "reason": "no limit defined for desk/risk type",
                 "severity": "HIGH"}
            )
            continue
        totals[key] = totals.get(key, 0.0) + pos.exposure_usd

    results = []
    for (desk, risk_type), limit in sorted(limit_map.items()):
        exposure = round(totals.get((desk, risk_type), 0.0), 2)
        util = utilisation(exposure, limit.limit_usd)
        results.append(
            LimitResult(desk, risk_type, exposure, limit.limit_usd,
                        round(util, 4), status_for(util))
        )
    return results, exceptions


def breaches(results: list[LimitResult]) -> list[LimitResult]:
    return [r for r in results if r.status == "BREACH"]


def warnings(results: list[LimitResult]) -> list[LimitResult]:
    return [r for r in results if r.status == "WARNING"]
