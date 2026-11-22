"""Reconciliation: CRM vs calculated vs paid, all four finding kinds."""
from decimal import Decimal

import pytest

from comp_engine import calculate, build_payments, reconcile
from conftest import deal


def _result(plan_v1, deal_id="D1", rep_id="R1", amount="100000", attainment="0.60"):
    return calculate(deal_id, rep_id, Decimal(amount), Decimal(attainment), plan_v1)


def test_clean_run_has_no_findings(plan_v1):
    deals = [deal()]
    results = [_result(plan_v1)]
    payments = build_payments(results, "2026-11")
    assert reconcile(deals, results, payments, "2026-11") == []


def test_missing_calculation_flagged(plan_v1):
    deals = [deal(), deal(deal_id="D2", rep_id="R2", amount="50000")]
    results = [_result(plan_v1)]
    payments = build_payments(results, "2026-11")
    findings = reconcile(deals, results, payments, "2026-11")
    assert any(f.kind == "missing_calculation" and f.entity_id == "D2" for f in findings)


def test_unknown_deal_flagged(plan_v1):
    deals = [deal()]
    results = [_result(plan_v1), _result(plan_v1, deal_id="D9")]
    payments = build_payments(results, "2026-11")
    findings = reconcile(deals, results, payments, "2026-11")
    assert any(f.kind == "unknown_deal" and f.entity_id == "D9" for f in findings)


def test_missing_payment_flagged(plan_v1):
    deals = [deal()]
    results = [_result(plan_v1)]
    findings = reconcile(deals, results, [], "2026-11")
    assert any(f.kind == "missing_payment" and f.entity_id == "R1" for f in findings)


def test_amount_mismatch_flagged(plan_v1):
    deals = [deal()]
    results = [_result(plan_v1)]
    payments = build_payments(results, "2026-11")
    payments[0].gross_commission = Decimal("1.00")  # simulate a payroll error
    findings = reconcile(deals, results, payments, "2026-11")
    assert any(f.kind == "amount_mismatch" and f.entity_id == "R1" for f in findings)


def test_refunded_deal_needs_no_calculation(plan_v1):
    deals = [deal(status="refunded")]
    findings = reconcile(deals, [], [], "2026-11")
    assert findings == []


def test_other_period_payments_ignored(plan_v1):
    deals = [deal()]
    results = [_result(plan_v1)]
    payments = build_payments(results, "2026-10")  # wrong period
    findings = reconcile(deals, results, payments, "2026-11")
    assert any(f.kind == "missing_payment" for f in findings)
