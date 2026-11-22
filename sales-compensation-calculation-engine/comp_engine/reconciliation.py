"""Reconciliation: compare what the CRM says was booked, what the engine
calculated, and what payroll paid. Any mismatch is a finding with a
named cause, so finance can trace every dollar.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import CommissionResult, Deal, Payment


@dataclass(frozen=True)
class Finding:
    entity_id: str
    kind: str        # missing_calculation | missing_payment | amount_mismatch | unknown_deal
    detail: str


def reconcile(deals: list[Deal], results: list[CommissionResult],
              payments: list[Payment], period: str) -> list[Finding]:
    """Cross-check the three sources for one payout period.

    - every closed_won deal must have a commission result
    - every result must be covered by a payment for its rep
    - the payment gross for a rep must equal the sum of that rep's results
    - a result for a deal nobody booked is flagged
    """
    findings: list[Finding] = []
    result_by_deal = {r.deal_id: r for r in results}
    deal_ids = {d.deal_id for d in deals}

    for deal in deals:
        if deal.status == "closed_won" and deal.deal_id not in result_by_deal:
            findings.append(Finding(
                deal.deal_id, "missing_calculation",
                f"closed_won deal {deal.deal_id} has no commission result"))

    for result in results:
        if result.deal_id not in deal_ids:
            findings.append(Finding(
                result.deal_id, "unknown_deal",
                f"commission result for deal {result.deal_id}, which is not in CRM"))

    pay_by_rep = {p.rep_id: p for p in payments if p.period == period}
    totals: dict[str, Decimal] = {}
    for result in results:
        totals[result.rep_id] = totals.get(result.rep_id, Decimal("0")) + result.net_commission

    for rep_id, total in totals.items():
        payment = pay_by_rep.get(rep_id)
        if payment is None:
            findings.append(Finding(
                rep_id, "missing_payment",
                f"rep {rep_id} has {total} net commission but no payment for {period}"))
        elif payment.gross_commission != total:
            findings.append(Finding(
                rep_id, "amount_mismatch",
                f"rep {rep_id}: payment gross {payment.gross_commission} != "
                f"calculated net {total} for {period}"))
    return findings
