"""Payments: holdback math, held reps, and the approval workflow."""
from decimal import Decimal

import pytest

from comp_engine import calculate, build_payments, approve, mark_paid, release_hold
from comp_engine import Payment


def _results(plan_v1):
    r1 = calculate("D1", "R1", Decimal("100000"), Decimal("0.60"), plan_v1)
    r2 = calculate("D2", "R1", Decimal("50000"), Decimal("0.60"), plan_v1)
    r3 = calculate("D3", "R2", Decimal("200000"), Decimal("0.30"), plan_v1)
    return [r1, r2, r3]


def test_build_payments_aggregates_per_rep(plan_v1):
    payments = build_payments(_results(plan_v1), "2026-11")
    by_rep = {p.rep_id: p for p in payments}
    assert by_rep["R1"].gross_commission == Decimal("12000.00")
    assert by_rep["R2"].gross_commission == Decimal("12000.00")


def test_holdback_withheld_from_payable(plan_v1):
    payments = build_payments(_results(plan_v1), "2026-11")
    pay = next(p for p in payments if p.rep_id == "R1")
    assert pay.holdback == Decimal("1200.00")
    assert pay.payable == Decimal("10800.00")


def test_zero_holdback_pays_in_full(plan_v1):
    payments = build_payments(_results(plan_v1), "2026-11", holdback_pct=Decimal("0"))
    assert all(p.payable == p.gross_commission for p in payments)


def test_held_rep_payment_is_held(plan_v1):
    payments = build_payments(_results(plan_v1), "2026-11", held_rep_ids={"R2"})
    by_rep = {p.rep_id: p for p in payments}
    assert by_rep["R2"].status == "held"
    assert by_rep["R1"].status == "scheduled"


def test_approve_then_pay(plan_v1):
    payment = build_payments(_results(plan_v1), "2026-11")[0]
    approve(payment)
    assert payment.status == "approved"
    mark_paid(payment)
    assert payment.status == "paid"


def test_cannot_pay_before_approve(plan_v1):
    payment = build_payments(_results(plan_v1), "2026-11")[0]
    with pytest.raises(ValueError):
        mark_paid(payment)


def test_cannot_approve_held_payment(plan_v1):
    payment = build_payments(_results(plan_v1), "2026-11", held_rep_ids={"R1"})[0]
    with pytest.raises(ValueError):
        approve(payment)
    release_hold(payment)
    assert payment.status == "scheduled"
    approve(payment)
    assert payment.status == "approved"


def test_negative_net_commission_yields_no_holdback(plan_v1):
    r = calculate("D1", "R1", Decimal("1000"), Decimal("0.10"), plan_v1)
    from comp_engine import apply_adjustments
    apply_adjustments(r, Decimal("-5000"))
    payments = build_payments([r], "2026-11")
    assert payments[0].gross_commission == Decimal("-4940.00")
    assert payments[0].holdback == Decimal("0")
