"""Campaign planning dataset: budgets, flights and channel allocation.

The planning tools the Performance Marketing team uses start here: a
campaign plan turns a total budget, a flight (start/end) and a target CPA
into a day-by-day plan the pipelines can measure actuals against.

Spark mapping: build_plan is a GROUP BY over the campaign dimension with
date arithmetic (datediff / sequence) for the flight; allocate_budget is
a windowed share calculation over the plan.
"""

from __future__ import annotations

from datetime import date, timedelta


def _parse_day(value: str) -> date:
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)


def flight_days(start: str, end: str) -> int:
    """Inclusive number of days in a flight; must be at least 1."""
    days = (_parse_day(end) - _parse_day(start)).days + 1
    if days < 1:
        raise ValueError("flight end must be on or after flight start")
    return days


def build_plan(campaigns: list[dict]) -> list[dict]:
    """One plan row per campaign: daily budget and expected conversions.

    Each campaign needs campaign_id, platform, total_budget (> 0),
    flight_start, flight_end and target_cpa (> 0). Daily budget is the
    total spread evenly across the flight; expected daily conversions are
    daily budget / target CPA.
    """
    plan: list[dict] = []
    for campaign in campaigns:
        for field in ("campaign_id", "platform", "total_budget",
                      "flight_start", "flight_end", "target_cpa"):
            if field not in campaign:
                raise ValueError(f"campaign missing required field: {field}")
        if campaign["total_budget"] <= 0:
            raise ValueError("total_budget must be positive")
        if campaign["target_cpa"] <= 0:
            raise ValueError("target_cpa must be positive")
        days = flight_days(campaign["flight_start"], campaign["flight_end"])
        daily_budget = round(campaign["total_budget"] / days, 2)
        plan.append({
            "campaign_id": campaign["campaign_id"],
            "platform": campaign["platform"],
            "total_budget": campaign["total_budget"],
            "flight_start": campaign["flight_start"],
            "flight_end": campaign["flight_end"],
            "flight_days": days,
            "daily_budget": daily_budget,
            "target_cpa": campaign["target_cpa"],
            "expected_daily_conversions": round(daily_budget / campaign["target_cpa"], 2),
            "target_reach": campaign.get("target_reach"),
        })
    return plan


def allocate_budget(plan: list[dict], weights: dict[str, float]) -> list[dict]:
    """Reallocate the plan's total budget across platforms by weight.

    Weights must cover every platform in the plan and sum to 1.0 (within
    rounding). Returns new plan rows with reallocated total/daily budgets.
    """
    platforms = {row["platform"] for row in plan}
    if set(weights) != platforms:
        raise ValueError("weights must cover exactly the plan platforms")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1.0")
    total = sum(row["total_budget"] for row in plan)
    out: list[dict] = []
    for row in plan:
        new_total = round(total * weights[row["platform"]], 2)
        new_row = dict(row)
        new_row["total_budget"] = new_total
        new_row["daily_budget"] = round(new_total / row["flight_days"], 2)
        new_row["expected_daily_conversions"] = round(
            new_row["daily_budget"] / row["target_cpa"], 2)
        out.append(new_row)
    return out


def plan_as_frame(plan: list[dict]):
    """Plan rows as a pandas DataFrame (Spark: the campaign plan table)."""
    import pandas as pd

    return pd.DataFrame(plan)
