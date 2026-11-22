"""Crediting rules: decide how much of a deal's amount counts toward each
rep's quota. A deal credits its owner, split partners take their share,
and refunded/churned deals credit nothing.
"""
from __future__ import annotations

from decimal import Decimal

from .models import Deal, Rep

NON_CREDITING_STATUSES = {"refunded", "churned", "pending"}


def credit_deal(deal: Deal, reps: dict[str, Rep]) -> dict[str, Decimal]:
    """Return {rep_id: credited_amount} for one deal.

    Rules:
    - refunded / churned / pending deals credit $0 to everyone.
    - split_pct of the amount goes to the split partners, divided equally;
      the owner keeps the rest.
    - a split partner who is not a known rep is ignored (their share is
      dropped, never silently given to the owner).
    """
    if deal.status in NON_CREDITING_STATUSES:
        return {}
    if deal.rep_id not in reps:
        raise ValueError(f"deal {deal.deal_id}: unknown owner rep {deal.rep_id}")
    if deal.amount < 0:
        raise ValueError(f"deal {deal.deal_id}: negative amount {deal.amount}")

    credited: dict[str, Decimal] = {}
    named = [r for r in deal.split_with if r != deal.rep_id]
    known = [r for r in named if r in reps]
    if named and deal.split_pct > 0:
        share = (deal.amount * deal.split_pct / len(named)).quantize(Decimal("0.01"))
        owner_amount = deal.amount - share * len(named)
        for partner in known:
            credited[partner] = share
    else:
        owner_amount = deal.amount
    credited[deal.rep_id] = owner_amount
    return credited


def quota_attainment(rep: Rep, credited_total: Decimal) -> Decimal:
    """Attainment as a fraction of quota (e.g. 1.25 = 125%)."""
    if rep.quota <= 0:
        raise ValueError(f"rep {rep.rep_id}: quota must be positive")
    return (credited_total / rep.quota).quantize(Decimal("0.0001"))
