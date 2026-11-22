"""Commission calculation: tiered rates, accelerators, caps.

A deal pays the rate of the tier its rep's attainment falls in, applied to
the credited amount. Attainment above the accelerator threshold earns the
accelerator multiplier on the portion above the threshold. A per-deal cap
bounds the result. All money uses Decimal and rounds to cents.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .models import CommissionResult, CompPlan, Tier

CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def rate_for(attainment: Decimal, tiers: tuple[Tier, ...]) -> Decimal:
    """Highest tier whose threshold the attainment has reached."""
    rate = tiers[0].rate
    for tier in tiers:
        if attainment >= tier.attainment_threshold:
            rate = tier.rate
        else:
            break
    return rate


def calculate(deal_id: str, rep_id: str, credited_amount: Decimal,
              attainment: Decimal, plan: CompPlan) -> CommissionResult:
    """Calculate gross commission for one credited deal."""
    if credited_amount < 0:
        raise ValueError(f"deal {deal_id}: negative credited amount")
    rate = rate_for(attainment, plan.tiers)
    gross = credited_amount * rate

    # Accelerator: the slice of credited amount above the threshold
    # attainment earns the multiplier instead of the plain rate.
    if attainment > plan.accelerator_threshold and plan.accelerator_multiplier > 1:
        threshold_amount = plan.accelerator_threshold / attainment * credited_amount
        base_slice = threshold_amount * rate
        accel_slice = (credited_amount - threshold_amount) * rate * plan.accelerator_multiplier
        gross = base_slice + accel_slice

    gross = _money(gross)
    capped = False
    if plan.cap is not None and gross > plan.cap:
        gross = plan.cap
        capped = True

    return CommissionResult(
        deal_id=deal_id,
        rep_id=rep_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        credited_amount=_money(credited_amount),
        attainment=attainment,
        rate=rate,
        gross_commission=gross,
        capped=capped,
    )


def apply_adjustments(result: CommissionResult, adjustment_total: Decimal) -> CommissionResult:
    """Attach the signed adjustment total (clawbacks negative) to a result."""
    result.adjustments = _money(adjustment_total)
    result.net_commission = _money(result.gross_commission + result.adjustments)
    return result
