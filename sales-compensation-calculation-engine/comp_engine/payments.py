"""Payment workflow: turn net commissions into a payroll-ready payout
schedule. A holdback percentage is withheld until the clawback window
passes; payments move scheduled -> approved -> paid, and a rep with an
open clawback has their payment held.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .models import CommissionResult, Payment

CENT = Decimal("0.01")


def build_payments(results: list[CommissionResult], period: str,
                   holdback_pct: Decimal = Decimal("0.10"),
                   held_rep_ids: set[str] | None = None) -> list[Payment]:
    """Aggregate net commissions per rep into one payment per rep."""
    held = held_rep_ids or set()
    totals: dict[str, Decimal] = {}
    for result in results:
        totals[result.rep_id] = totals.get(result.rep_id, Decimal("0")) + result.net_commission

    payments: list[Payment] = []
    for rep_id in sorted(totals):
        gross = totals[rep_id].quantize(CENT, rounding=ROUND_HALF_UP)
        holdback = (gross * holdback_pct).quantize(CENT, rounding=ROUND_HALF_UP) if gross > 0 else Decimal("0")
        payments.append(Payment(
            payment_id=f"PAY-{period}-{rep_id}",
            rep_id=rep_id,
            period=period,
            gross_commission=gross,
            holdback=holdback,
            payable=gross - holdback,
            status="held" if rep_id in held else "scheduled",
        ))
    return payments


def approve(payment: Payment) -> Payment:
    if payment.status != "scheduled":
        raise ValueError(f"payment {payment.payment_id}: cannot approve from {payment.status}")
    payment.status = "approved"
    return payment


def mark_paid(payment: Payment) -> Payment:
    if payment.status != "approved":
        raise ValueError(f"payment {payment.payment_id}: cannot pay from {payment.status}")
    payment.status = "paid"
    return payment


def release_hold(payment: Payment) -> Payment:
    if payment.status != "held":
        raise ValueError(f"payment {payment.payment_id}: cannot release from {payment.status}")
    payment.status = "scheduled"
    return payment
