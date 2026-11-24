"""SLI/SLO definitions, error-budget burn-rate alerting, and capacity planning.

Added Nov 24, 2026, for an AppFolio Sr. Site Reliability & Infrastructure
Engineer application. AppFolio's posting asks for SLI/SLO experience,
error-budget thinking, capacity planning, monitoring/alerting, runbooks and
disaster recovery for highly available distributed SaaS services on AWS.

Everything here runs on synthetic input data only. No real service, cluster,
or monitoring tool is contacted, and no production SRE experience is claimed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# SLI / SLO
# ---------------------------------------------------------------------------

@dataclass
class SLO:
    """A service level objective for one service level indicator.

    ``target`` is the fraction of good events required over ``window_days``
    (e.g. 0.999 for 99.9% availability over 30 days). The error budget is
    ``1 - target`` of all events in the window.
    """

    name: str
    target: float
    window_days: int = 30
    description: str = ""

    def __post_init__(self) -> None:
        if not 0.0 < self.target < 1.0:
            raise ValueError("SLO target must be between 0 and 1 (exclusive)")
        if self.window_days <= 0:
            raise ValueError("window_days must be positive")

    @property
    def error_budget_fraction(self) -> float:
        """Fraction of events allowed to be bad inside the window."""
        return 1.0 - self.target

    def allowed_bad_events(self, total_events: int) -> float:
        """How many bad events the budget allows for this many total events."""
        if total_events < 0:
            raise ValueError("total_events must not be negative")
        return total_events * self.error_budget_fraction


def error_budget_remaining(slo: SLO, good_events: int, total_events: int) -> dict:
    """How much of the SLO error budget is left, given observed events.

    Returns the observed availability, the budget consumed so far as a
    fraction of the whole budget, and a plain-word status: "healthy" while
    less than half the budget is spent, "watch" past half, "exhausted" once
    the budget is fully spent (availability below target).
    """
    if total_events <= 0:
        raise ValueError("total_events must be positive")
    if not 0 <= good_events <= total_events:
        raise ValueError("good_events must be between 0 and total_events")
    bad_events = total_events - good_events
    availability = good_events / total_events
    budget = slo.allowed_bad_events(total_events)
    consumed = bad_events / budget if budget > 0 else 0.0
    if availability >= slo.target:
        status = "healthy" if consumed < 0.5 else "watch"
    else:
        status = "exhausted"
    return {
        "slo": slo.name,
        "target": slo.target,
        "availability": round(availability, 6),
        "error_budget": round(budget, 2),
        "bad_events": bad_events,
        "budget_consumed": round(consumed, 4),
        "remaining_budget_events": round(max(budget - bad_events, 0.0), 2),
        "status": status,
    }


# ---------------------------------------------------------------------------
# Multi-window burn-rate alerting
# ---------------------------------------------------------------------------

# (window label, burn-rate threshold, alert severity) following the
# multi-window multi-burn-rate pattern: a fast burn pages, a slow burn
# opens a ticket so the team can act before the budget is gone.
BURN_ALERT_RULES = [
    ("1h", 14.4, "page"),
    ("6h", 6.0, "page"),
    ("3d", 1.0, "ticket"),
]


def burn_rate(slo: SLO, good_events: int, total_events: int) -> float:
    """How fast the error budget is being spent: 1.0 means exactly on budget.

    A burn rate of 14.4 over one hour spends the whole 30-day budget in
    about two days; 6.0 over six hours spends it in about five days.
    """
    if total_events <= 0:
        raise ValueError("total_events must be positive")
    if not 0 <= good_events <= total_events:
        raise ValueError("good_events must be between 0 and total_events")
    observed_bad_fraction = (total_events - good_events) / total_events
    budget_fraction = slo.error_budget_fraction
    return round(observed_bad_fraction / budget_fraction, 4)


def evaluate_burn_windows(slo: SLO, windows: dict) -> list:
    """Evaluate burn rate per window and return the alerts that fire.

    ``windows`` maps a window label ("1h", "6h", "3d") to a
    ``(good_events, total_events)`` pair. Returns one dict per fired rule
    with the window, burn rate, threshold and severity. An empty list means
    no alert fires.
    """
    alerts = []
    for label, threshold, severity in BURN_ALERT_RULES:
        if label not in windows:
            continue
        good_events, total_events = windows[label]
        rate = burn_rate(slo, good_events, total_events)
        if rate >= threshold:
            alerts.append(
                {
                    "window": label,
                    "burn_rate": rate,
                    "threshold": threshold,
                    "severity": severity,
                    "action": "page on-call" if severity == "page" else "open ticket",
                }
            )
    return alerts


# ---------------------------------------------------------------------------
# Capacity planning
# ---------------------------------------------------------------------------

@dataclass
class CapacityPlan:
    """Capacity headroom forecast for one resource (CPU, connections, disk).

    ``history`` is a list of daily usage values in the same unit as
    ``capacity`` (oldest first). Growth is fitted as a simple daily increase
    from the first to the last value, so the forecast is transparent and
    easy to check by hand. ``headroom_target`` is the usage fraction at
    which the team wants to have scaled out already (e.g. 0.70).
    """

    resource: str
    capacity: float
    history: list = field(default_factory=list)
    headroom_target: float = 0.70

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if not 0.0 < self.headroom_target < 1.0:
            raise ValueError("headroom_target must be between 0 and 1")
        if any(v < 0 for v in self.history):
            raise ValueError("history values must not be negative")

    @property
    def current_usage(self) -> float:
        return self.history[-1] if self.history else 0.0

    @property
    def current_utilization(self) -> float:
        return self.current_usage / self.capacity

    @property
    def daily_growth(self) -> float:
        """Average daily increase in usage across the observed history."""
        if len(self.history) < 2:
            return 0.0
        return (self.history[-1] - self.history[0]) / (len(self.history) - 1)

    def days_until_full(self) -> float | None:
        """Days until usage reaches capacity at the fitted growth rate.

        Returns None when usage is flat or falling (no saturation in sight).
        """
        growth = self.daily_growth
        if growth <= 0:
            return None
        return (self.capacity - self.current_usage) / growth

    def days_until_headroom_target(self) -> float | None:
        """Days until usage reaches the headroom target (time to scale out)."""
        growth = self.daily_growth
        if growth <= 0:
            return None
        target_usage = self.capacity * self.headroom_target
        if self.current_usage >= target_usage:
            return 0.0
        return (target_usage - self.current_usage) / growth

    def forecast(self, days_ahead: int = 30) -> dict:
        """Headroom forecast with a plain-word recommendation."""
        if days_ahead <= 0:
            raise ValueError("days_ahead must be positive")
        growth = self.daily_growth
        projected = self.current_usage + growth * days_ahead
        projected_utilization = projected / self.capacity
        days_full = self.days_until_full()
        days_target = self.days_until_headroom_target()
        if projected_utilization >= 1.0:
            recommendation = "scale out now: projected to exceed capacity"
        elif days_target is not None and days_target <= days_ahead:
            recommendation = "plan scale-out: headroom target reached inside the forecast window"
        elif growth <= 0:
            recommendation = "no action: usage flat or falling"
        else:
            recommendation = "no action: headroom holds for the forecast window"
        return {
            "resource": self.resource,
            "capacity": self.capacity,
            "current_usage": round(self.current_usage, 2),
            "current_utilization": round(self.current_utilization, 4),
            "daily_growth": round(growth, 4),
            "projected_usage_in_days": round(projected, 2),
            "projected_utilization": round(projected_utilization, 4),
            "days_until_full": None if days_full is None else round(days_full, 1),
            "days_until_headroom_target": None if days_target is None else round(days_target, 1),
            "recommendation": recommendation,
        }
