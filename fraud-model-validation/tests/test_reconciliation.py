"""Tests for the financial-flow reconciliation module."""

import numpy as np
import pandas as pd

from fraud_validation.reconciliation import (
    break_aging,
    build_reconciliation_section,
    capital_flow_summary,
    generate_ledger,
    reconcile,
)


def _tiny_ledger():
    ledger = pd.DataFrame({
        "txn_id": ["TXN-000001", "TXN-000002", "TXN-000003"],
        "flow": ["card_purchase", "refund", "payout"],
        "amount": [100.00, 25.50, 400.00],
        "value_day": [2, 5, 10],
    })
    return ledger


def test_clean_reconciliation_has_no_breaks():
    ledger = _tiny_ledger()
    summary, breaks = reconcile(ledger, ledger.copy())
    assert summary["n_matched"] == 3
    assert summary["n_breaks"] == 0
    assert breaks.empty
    assert summary["net_difference"] == 0.0


def test_amount_mismatch_detected():
    ledger = _tiny_ledger()
    flows = ledger.copy()
    flows.loc[flows["txn_id"] == "TXN-000002", "amount"] = 30.50
    summary, breaks = reconcile(ledger, flows)
    assert summary["n_amount_mismatch"] == 1
    assert summary["n_matched"] == 2
    assert set(breaks["break_type"]) == {"amount_mismatch"}
    assert breaks.iloc[0]["txn_id"] == "TXN-000002"


def test_missing_and_orphan_detected():
    ledger = _tiny_ledger()
    flows = ledger[ledger["txn_id"] != "TXN-000003"].copy()
    orphan = pd.DataFrame({
        "txn_id": ["ORPH-000001"], "flow": ["fee"],
        "amount": [9.99], "value_day": [7],
    })
    flows = pd.concat([flows, orphan], ignore_index=True)
    summary, breaks = reconcile(ledger, flows)
    assert summary["n_missing_in_flows"] == 1
    assert summary["n_orphan_flow"] == 1
    assert set(breaks["break_type"]) == {"missing_in_flows", "orphan_flow"}


def test_duplicate_posting_detected():
    ledger = _tiny_ledger()
    flows = pd.concat([ledger, ledger.iloc[[0]]], ignore_index=True)
    summary, breaks = reconcile(ledger, flows)
    assert summary["n_duplicate_posting"] == 1
    assert summary["n_matched"] == 3
    assert (breaks["break_type"] == "duplicate_posting").sum() == 1


def test_generated_ledger_break_rate_under_threshold():
    ledger, flows = generate_ledger()
    summary, breaks = reconcile(ledger, flows)
    assert summary["n_ledger"] == 5_000
    assert summary["n_breaks"] == len(breaks)
    assert summary["break_rate"] < 0.02
    assert summary["n_amount_mismatch"] > 0
    assert summary["n_missing_in_flows"] > 0
    assert summary["n_orphan_flow"] > 0


def test_capital_flow_totals_reconcile_when_clean():
    ledger = _tiny_ledger()
    out = capital_flow_summary(ledger, ledger.copy())
    assert set(out["flow"]) == {"card_purchase", "refund", "payout"}
    assert np.allclose(out["difference"].to_numpy(), 0.0)
    assert int(out.loc[out["flow"] == "refund", "n_ledger"].iloc[0]) == 1


def test_break_aging_buckets_cover_all_breaks():
    ledger, flows = generate_ledger()
    _, breaks = reconcile(ledger, flows)
    aging = break_aging(breaks, as_of_day=30)
    assert set(aging["age_bucket"]) == {"0-7 days", "8-14 days", "15-30 days"}
    assert int(aging["n_breaks"].sum()) == len(breaks)


def test_reconciliation_section_reports_numbers():
    ledger, flows = generate_ledger()
    summary, breaks = reconcile(ledger, flows)
    section = build_reconciliation_section(
        summary, capital_flow_summary(ledger, flows), break_aging(breaks)
    )
    assert "12. FINANCIAL-FLOW RECONCILIATION" in section
    assert f"{summary['n_ledger']:,}" in section
    assert "card_purchase" in section
    assert "Verdict" in section
