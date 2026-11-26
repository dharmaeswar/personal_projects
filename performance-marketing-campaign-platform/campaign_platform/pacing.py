"""Budget pacing and in-flight optimisation safeguards.

Two questions the team asks every day: is this campaign spending on pace
with its flight, and is it safe to apply the next optimisation to the
live campaign? Pacing compares actual spend-to-date with the spend the
plan expects by today. Safeguards HOLD an optimisation when a guardrail
breaks, so a bad bid or budget change never reaches an in-flight campaign
unchecked. Every hold names its reason and needs a human review.

Spark mapping: pacing_status is a windowed cumulative SUM(spend) over the
flight joined to the plan; guardrails are filter predicates on the joined
actuals.
"""

from __future__ import annotations

# A campaign more than 20% ahead of or behind plan is off pace.
PACE_TOLERANCE = 0.20
# An optimisation is held when realised CPA is 1.5x the target or worse.
CPA_HOLD_MULTIPLIER = 1.5
# A single-day spend spike above 2x the daily budget is treated as anomalous.
SPIKE_MULTIPLIER = 2.0


def pacing_status(plan_row: dict, actual_spend_to_date: float,
                  day_index: int) -> dict:
    """Pacing for one campaign on day `day_index` (1-based) of its flight.

    expected_spend is the plan's daily budget times days elapsed.
    status is on-track within +/-20%, ahead when spending too fast,
    behind when spending too slowly.
    """
    if day_index < 1 or day_index > plan_row["flight_days"]:
        raise ValueError("day_index outside the flight")
    if actual_spend_to_date < 0:
        raise ValueError("actual spend must be non-negative")
    expected = round(plan_row["daily_budget"] * day_index, 2)
    variance = 0.0 if expected == 0 else round(
        (actual_spend_to_date - expected) / expected, 4)
    if variance > PACE_TOLERANCE:
        status = "ahead"
    elif variance < -PACE_TOLERANCE:
        status = "behind"
    else:
        status = "on-track"
    return {
        "campaign_id": plan_row["campaign_id"],
        "platform": plan_row["platform"],
        "day_index": day_index,
        "expected_spend": expected,
        "actual_spend": round(actual_spend_to_date, 2),
        "variance_pct": round(variance * 100, 2),
        "status": status,
    }


def optimisation_guardrails(plan_row: dict, actual_day: dict) -> dict:
    """Decide whether an optimisation may be applied to a live campaign.

    actual_day carries spend, conversions and impressions for the day.
    Returns ALLOW, or HOLD with every broken guardrail listed. A HOLD
    always requires human review before the optimisation is applied.
    """
    reasons: list[str] = []
    spend = actual_day.get("spend", 0.0)
    conversions = actual_day.get("conversions", 0)
    daily_budget = plan_row["daily_budget"]

    if spend > daily_budget * SPIKE_MULTIPLIER:
        reasons.append(
            f"spend spike: ${spend:,.2f} is over {SPIKE_MULTIPLIER}x "
            f"the ${daily_budget:,.2f} daily budget")
    if spend > 0 and conversions == 0:
        reasons.append("zero conversions on spend above $0")
    if conversions > 0:
        realised_cpa = spend / conversions
        if realised_cpa > plan_row["target_cpa"] * CPA_HOLD_MULTIPLIER:
            reasons.append(
                f"realised CPA ${realised_cpa:,.2f} exceeds "
                f"{CPA_HOLD_MULTIPLIER}x target CPA "
                f"${plan_row['target_cpa']:,.2f}")
    if actual_day.get("impressions", 0) > 0 and actual_day.get("clicks", 0) == 0:
        reasons.append("impressions with zero clicks (possible tracking break)")

    decision = "HOLD" if reasons else "ALLOW"
    return {
        "campaign_id": plan_row["campaign_id"],
        "decision": decision,
        "reasons": reasons,
        "requires_human_review": decision == "HOLD",
    }
