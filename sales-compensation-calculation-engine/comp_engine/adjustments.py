"""Adjustments: clawbacks, manual adjustments and SPIFFs.

- A clawback fires when a deal is refunded or churned inside the plan's
  clawback window after close; it reverses the commission already paid.
- Manual adjustments need an approver; unapproved ones are rejected.
- SPIFFs are one-off bonuses tied to a deal, never negative.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import Adjustment, CompPlan, Deal


class AdjustmentError(ValueError):
    pass


def clawback_for(deal: Deal, commission_paid: Decimal, plan: CompPlan,
                 event_date: date) -> Adjustment | None:
    """Build the clawback adjustment for a refund/churn event, or None if
    the event is outside the clawback window (commission stands)."""
    if deal.status not in ("refunded", "churned"):
        return None
    days = (event_date - deal.close_date).days
    if days < 0:
        raise AdjustmentError(f"deal {deal.deal_id}: event before close date")
    if days > plan.clawback_days:
        return None
    return Adjustment(
        adjustment_id=f"CLAW-{deal.deal_id}",
        deal_id=deal.deal_id,
        rep_id=deal.rep_id,
        amount=-commission_paid,
        kind="clawback",
        reason=f"{deal.status} {days} days after close (window {plan.clawback_days}d)",
        effective_date=event_date,
    )


def manual_adjustment(adjustment_id: str, deal_id: str, rep_id: str,
                      amount: Decimal, reason: str,
                      approved_by: str | None,
                      effective_date: date | None = None) -> Adjustment:
    if approved_by is None:
        raise AdjustmentError(f"adjustment {adjustment_id}: manual adjustments need an approver")
    if amount == 0:
        raise AdjustmentError(f"adjustment {adjustment_id}: zero amount")
    return Adjustment(
        adjustment_id=adjustment_id,
        deal_id=deal_id,
        rep_id=rep_id,
        amount=amount,
        kind="manual",
        reason=reason,
        approved_by=approved_by,
        effective_date=effective_date,
    )


def spiff(adjustment_id: str, deal_id: str, rep_id: str, amount: Decimal,
          reason: str, effective_date: date | None = None) -> Adjustment:
    if amount <= 0:
        raise AdjustmentError(f"adjustment {adjustment_id}: SPIFF must be positive")
    return Adjustment(
        adjustment_id=adjustment_id,
        deal_id=deal_id,
        rep_id=rep_id,
        amount=amount,
        kind="spiff",
        reason=reason,
        effective_date=effective_date,
    )


def total_for_deal(adjustments: list[Adjustment], deal_id: str) -> Decimal:
    return sum((a.amount for a in adjustments if a.deal_id == deal_id), Decimal("0"))
