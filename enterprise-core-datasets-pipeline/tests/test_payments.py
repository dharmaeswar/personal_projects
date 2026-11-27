"""Tests for the payments-settlement feed (gateway transactions -> facts).

The feed models a payment processor's lifecycle: authorized -> captured ->
settled, with failed transactions settling nothing. fact_payments_daily is
the grain (date x payment_method x status) that settlement reconciliation
and the FIS Data Engineer II role project read from.
"""

from enterprise_core import analytics, seed as seed_mod
from enterprise_core.contracts import validate
from enterprise_core.pipeline import Warehouse
from enterprise_core.quality import run_checks, all_passed


def _run_full():
    feeds = seed_mod.seed_all()
    wh = Warehouse()
    for feed, rows in feeds.items():
        wh.ingest(feed, rows)
    wh.build_dims()
    wh.build_facts()
    return wh, feeds


def test_payments_contract_quarantines_each_defect_type():
    feeds = seed_mod.seed_all()
    _, bad = validate("payments", feeds["payments"])
    assert len(bad) == 6  # 2 negative amounts + 1 unknown method +
    # 1 settled above amount + 1 failed with settled amount + 1 future date
    reasons = {r["_reason"] for r in bad}
    assert any("amount_usd=-12.5" in r for r in reasons)
    assert any("settled_amount_usd=-5.0" in r for r in reasons)
    assert any("payment_method='crypto' not allowed" in r for r in reasons)
    assert any("settled_amount_usd exceeds amount_usd" in r for r in reasons)
    assert any("failed txn carries settled_amount_usd" in r for r in reasons)
    assert any("txn_date=2026-12-01" in r for r in reasons)


def test_payments_ingest_dedupes_redelivered_gateway_batches():
    feeds = seed_mod.seed_all()
    wh = Warehouse()
    result = wh.ingest("payments", feeds["payments"])
    assert result["duplicates_removed"] == 2  # the 2 re-delivered txn_ids
    assert result["quarantined"] == 6
    bronze = wh.tables["bronze_payments"]
    assert bronze["txn_id"].is_unique
    assert set(bronze["payment_method"]) == {"card", "ach", "wire", "wallet"}
    assert set(bronze["status"]) <= {"authorized", "captured", "settled", "failed"}


def test_fact_payments_daily_ties_to_bronze():
    wh, _ = _run_full()
    fact = wh.tables["fact_payments_daily"]
    bronze = wh.tables["bronze_payments"]
    assert int(fact["txn_count"].sum()) == len(bronze)
    assert abs(float(fact["gross_amount_usd"].sum())
               - float(bronze["amount_usd"].sum())) < 0.01
    assert abs(float(fact["settled_amount_usd"].sum())
               - float(bronze["settled_amount_usd"].sum())) < 0.01
    # Settled money never exceeds gross money, in any grain.
    assert (fact["settled_amount_usd"] <= fact["gross_amount_usd"] + 0.01).all()
    # Settlement lag is reported only on settled rows.
    non_settled = fact[fact["status"] != "settled"]
    assert (non_settled["avg_settlement_lag_days"] == 0.0).all()
    settled = fact[fact["status"] == "settled"]
    assert (settled["avg_settlement_lag_days"] > 0).all()
    assert (settled["avg_settlement_lag_days"] <= 2).all()


def test_dim_payment_method_covers_fact_methods():
    wh, _ = _run_full()
    dim = wh.tables["dim_payment_method"]
    fact = wh.tables["fact_payments_daily"]
    assert set(dim["payment_method"]) == set(fact["payment_method"])
    assert len(dim) == 4


def test_payments_checks_pass_and_backfill_covers_new_fact():
    from enterprise_core.backfill import plan_backfill

    wh, _ = _run_full()
    checks = run_checks(wh)
    assert all_passed(checks), [c for c in checks if not c["passed"]]
    plan = plan_backfill(wh, "payments", "2026-11-01", "2026-11-07")
    assert plan["affected_facts"] == ["fact_payments_daily"]


def test_payments_settlement_summary_rates_are_sane():
    wh, _ = _run_full()
    summary = analytics.payments_settlement_summary(wh)
    assert set(summary["payment_method"]) == {"card", "ach", "wire", "wallet"}
    assert ((summary["settlement_rate_pct"] >= 0)
            & (summary["settlement_rate_pct"] <= 100)).all()
    # Settled rows exist, so every method settled something.
    assert (summary["settled_amount_usd"] > 0).all()
