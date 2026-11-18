"""Arbitrage, consistency and staleness checks for a vol surface.

Checks implemented
------------------
* **Calendar arbitrage** -- for a fixed strike, total implied variance
  ``w(T) = sigma^2 * T`` must be non-decreasing in expiry ``T``. A decrease
  means a calendar spread could be locked in at a negative price.
* **Butterfly arbitrage** -- for a fixed expiry, call prices must be convex
  in strike; equivalently the implied risk-neutral density (the second
  strike-difference of call prices) must be non-negative.
* **Strike monotonicity** -- for a fixed expiry, call prices must be
  non-increasing in strike (put prices non-decreasing).
* **Stale quotes** -- a quote whose timestamp is older than a configurable
  maximum age relative to the surface's newest timestamp.
* **RMS smile error** -- per expiry, the root-mean-square difference between
  the quoted implied vols and a quadratic smile fitted in log-moneyness.
  Large residuals flag quotes that sit off the smooth surface and should be
  reviewed before calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .surface import Quote, Surface

CALENDAR = "calendar_arbitrage"
BUTTERFLY = "butterfly_arbitrage"
MONOTONICITY = "strike_monotonicity"
STALE = "stale_quote"
SMILE_RMS = "smile_rms_error"


@dataclass(frozen=True)
class Violation:
    """One failed check on one quote (or one strike/expiry node)."""

    check: str
    expiry: float
    strike: float
    detail: str
    severity: str = "high"

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "expiry": self.expiry,
            "strike": self.strike,
            "detail": self.detail,
            "severity": self.severity,
        }


def check_calendar(surface: Surface, tol: float = 1e-10) -> list[Violation]:
    """Total variance must be non-decreasing in T for each strike."""
    violations: list[Violation] = []
    strikes = sorted({q.strike for q in surface.quotes})
    for strike in strikes:
        chain = [q for q in surface.by_strike(strike) if q.option_type == "call"]
        for prev, curr in zip(chain, chain[1:]):
            if curr.total_variance < prev.total_variance - tol:
                violations.append(
                    Violation(
                        check=CALENDAR,
                        expiry=curr.expiry,
                        strike=strike,
                        detail=(
                            f"total variance falls from {prev.total_variance:.6f} "
                            f"(T={prev.expiry}) to {curr.total_variance:.6f} "
                            f"(T={curr.expiry}) at strike {strike:g}"
                        ),
                    )
                )
    return violations


def check_butterfly(surface: Surface, tol: float = 1e-9) -> list[Violation]:
    """Call prices must be convex in strike at each expiry.

    Uses the slope form of convexity, which handles unequally spaced
    strikes: for consecutive strikes K1 < K2 < K3 the slope
    (C2 - C1)/(K2 - K1) must not exceed (C3 - C2)/(K3 - K2). A violation is
    a negative implied density at the middle strike.
    """
    violations: list[Violation] = []
    for expiry in surface.expiries:
        chain = [q for q in surface.by_expiry(expiry) if q.option_type == "call"]
        for q1, q2, q3 in zip(chain, chain[1:], chain[2:]):
            slope_left = (q2.market_price - q1.market_price) / (q2.strike - q1.strike)
            slope_right = (q3.market_price - q2.market_price) / (q3.strike - q2.strike)
            density = slope_right - slope_left
            if density < -tol:
                violations.append(
                    Violation(
                        check=BUTTERFLY,
                        expiry=expiry,
                        strike=q2.strike,
                        detail=(
                            f"negative implied density {density:.6f} at strike "
                            f"{q2.strike:g} (T={expiry}): call prices not convex "
                            f"in strike"
                        ),
                    )
                )
    return violations


def check_monotonicity(surface: Surface, tol: float = 1e-9) -> list[Violation]:
    """Call prices must be non-increasing in strike at each expiry."""
    violations: list[Violation] = []
    for expiry in surface.expiries:
        chain = [q for q in surface.by_expiry(expiry) if q.option_type == "call"]
        for lower, higher in zip(chain, chain[1:]):
            if higher.market_price > lower.market_price + tol:
                violations.append(
                    Violation(
                        check=MONOTONICITY,
                        expiry=expiry,
                        strike=higher.strike,
                        detail=(
                            f"call price rises from {lower.market_price:.4f} at "
                            f"strike {lower.strike:g} to {higher.market_price:.4f} "
                            f"at strike {higher.strike:g} (T={expiry})"
                        ),
                    )
                )
    return violations


def check_stale(
    surface: Surface,
    max_age_hours: float = 24.0,
    as_of: datetime | None = None,
) -> list[Violation]:
    """Flag quotes older than ``max_age_hours`` relative to ``as_of``.

    ``as_of`` defaults to the newest timestamp on the surface, so a quote
    left behind by a feed outage is flagged against its own file.
    """
    reference = as_of or surface.as_of
    violations: list[Violation] = []
    for q in surface.quotes:
        age_hours = (reference - q.timestamp).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            violations.append(
                Violation(
                    check=STALE,
                    expiry=q.expiry,
                    strike=q.strike,
                    detail=(
                        f"quote timestamp {q.timestamp.isoformat()} is "
                        f"{age_hours:.1f}h old (limit {max_age_hours:g}h) "
                        f"at strike {q.strike:g}, T={q.expiry}"
                    ),
                    severity="medium",
                )
            )
    return violations


def smile_rms_error(quotes: list[Quote]) -> float:
    """RMS residual of quoted IVs vs a quadratic smile in log-moneyness.

    Fits ``sigma(k) = a + b*k + c*k^2`` with ``k = log(K/F)`` by least
    squares and returns the root-mean-square residual, in vol points.
    With fewer than 4 quotes the fit is under-determined and 0.0 is
    returned (no smile diagnostic available).
    """
    if len(quotes) < 4:
        return 0.0
    k = np.array([q.log_moneyness for q in quotes])
    sigma = np.array([q.implied_vol for q in quotes])
    design = np.column_stack([np.ones_like(k), k, k * k])
    coeffs, *_ = np.linalg.lstsq(design, sigma, rcond=None)
    residuals = sigma - design @ coeffs
    return float(np.sqrt(np.mean(residuals**2)))


def smile_rms_by_expiry(surface: Surface) -> dict[float, float]:
    """RMS smile error for every expiry on the surface."""
    return {
        expiry: smile_rms_error(
            [q for q in surface.by_expiry(expiry) if q.option_type == "call"]
        )
        for expiry in surface.expiries
    }


@dataclass
class CheckReport:
    """Aggregate result of running every check over a surface."""

    violations: list[Violation] = field(default_factory=list)
    rms_by_expiry: dict[float, float] = field(default_factory=dict)
    quotes_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def counts_by_check(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.violations:
            counts[v.check] = counts.get(v.check, 0) + 1
        return counts


def run_all_checks(
    surface: Surface,
    max_age_hours: float = 24.0,
    as_of: datetime | None = None,
    on_violation=None,
) -> CheckReport:
    """Run every check; ``on_violation`` (if given) fires per violation.

    The callback is the hook the alerts module uses to emit a fast alert
    the moment a check fails, rather than after the whole batch finishes.
    """
    violations: list[Violation] = []
    for found in (
        check_calendar(surface),
        check_butterfly(surface),
        check_monotonicity(surface),
        check_stale(surface, max_age_hours=max_age_hours, as_of=as_of),
    ):
        for v in found:
            violations.append(v)
            if on_violation is not None:
                on_violation(v)
    return CheckReport(
        violations=violations,
        rms_by_expiry=smile_rms_by_expiry(surface),
        quotes_checked=len(surface),
    )
