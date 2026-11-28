"""Tests for the regulated savings data platform.

Deterministic: all fixtures use the seeded synthetic data (seed 42).
"""
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from savings_platform import ingest, pipeline, governance  # noqa: E402


@pytest.fixture(scope="module")
def data():
    accounts = ingest.make_accounts()
    batch = ingest.make_contribution_batch(accounts)
    stream = ingest.make_stream_events(accounts)
    investments = ingest.make_investments(accounts)
    silver = pipeline.build_silver(accounts, batch, stream)
    gold = pipeline.build_gold(silver, investments)
    return {
        "accounts": accounts, "batch": batch, "stream": stream,
        "investments": investments, "silver": silver, "gold": gold,
    }


# ---------------------------------------------------------------- ingest
def test_accounts_shape_and_uniqueness(data):
    accounts = data["accounts"]
    assert len(accounts) == 120
    assert accounts["account_id"].is_unique
    assert set(accounts["program"]) <= {"core-savings", "education-savings"}
    assert set(accounts["status"]) <= {"active", "suspended", "closed"}


def test_batch_has_seeded_bad_rows(data):
    batch = data["batch"]
    assert (batch["amount"] < 0).sum() >= 1
    assert (batch["account_id"] == "ACC-99999").sum() >= 1
    assert batch["event_date"].isna().sum() >= 1


def test_stream_has_duplicate_delivery(data):
    stream = data["stream"]
    assert stream["event_id"].duplicated().sum() >= 1


def test_investments_reference_known_accounts(data):
    inv = data["investments"]
    assert set(inv["account_id"]) <= set(data["accounts"]["account_id"])
    assert (inv["units"] > 0).all()
    assert (inv["unit_price"] > 0).all()


# ---------------------------------------------------------------- pipeline
def test_dedupe_keeps_latest_delivery(data):
    deduped = pipeline.dedupe_latest(data["batch"])
    assert deduped["event_id"].is_unique
    # 600 batch rows + 12 re-deliveries -> 600 unique events.
    assert len(deduped) == 600


def test_quarantine_catches_all_bad_rows(data):
    silver = data["silver"]
    q = silver["quarantine"]
    assert len(q) > 0
    assert set(q["quarantine_reason"]) <= {
        "missing_event_date", "non_positive_amount", "unknown_account"}
    # No quarantined row leaks into silver events.
    assert not set(q["event_id"]) & set(silver["events"]["event_id"])


def test_silver_amounts_all_positive(data):
    events = data["silver"]["events"]
    assert (events["amount"] > 0).all()
    assert events["event_date"].notna().all()
    assert set(events["account_id"]) <= set(data["accounts"]["account_id"])


def test_silver_event_ids_unique(data):
    assert data["silver"]["events"]["event_id"].is_unique


def test_scd2_history_one_open_row_per_account(data):
    history, closed = pipeline.scd2_status_history(data["accounts"])
    assert history["is_current"].all()
    assert len(history) == len(data["accounts"])
    assert closed == 0


def test_gold_balances_reconcile_to_silver(data):
    recon = governance.reconcile_balances(data["gold"], data["silver"])
    assert recon["break_count"] == 0
    assert recon["total_diff"] == 0.0
    assert recon["checked_accounts"] == 120


def test_gold_balance_formula(data):
    balances = data["gold"]["account_balances"]
    row = balances.iloc[0]
    assert row["balance"] == round(
        row["total_contributions"] - row["total_disbursements"]
        + row["investment_value"], 2)


def test_gold_monthly_totals_match_silver(data):
    monthly = data["gold"]["monthly_contributions"]
    silver_total = data["silver"]["events"].query(
        "event_type == 'contribution'")["amount"].sum()
    assert abs(monthly["monthly_contributions"].sum() - silver_total) < 0.01


def test_program_totals_cover_both_programs(data):
    programs = set(data["gold"]["program_totals"]["program"])
    assert programs == {"core-savings", "education-savings"}


def test_write_tables_creates_parquet_and_log(tmp_path, data):
    tables = {"account_balances": data["gold"]["account_balances"]}
    entries = pipeline.write_tables(tables, str(tmp_path))
    assert (tmp_path / "account_balances.parquet").exists()
    assert (tmp_path / "_delta_log.json").exists()
    assert entries[0]["table"] == "account_balances"
    assert entries[0]["rows"] == len(data["gold"]["account_balances"])
    reread = pd.read_parquet(tmp_path / "account_balances.parquet")
    assert len(reread) == 120


# ---------------------------------------------------------------- lineage / audit
def test_lineage_covers_every_silver_row(data):
    lineage = governance.build_lineage(data["silver"])
    assert len(lineage) == len(data["silver"]["events"])
    assert set(lineage["silver_key"]) == set(data["silver"]["events"]["event_id"])
    assert lineage["source_system"].isin(
        ["batch-file", "kafka-topic/savings-events"]).all()


def test_audit_log_appends_without_overwrite(tmp_path):
    governance.append_audit_log(str(tmp_path), [{"run": "a"}])
    governance.append_audit_log(str(tmp_path), [{"run": "b"}])
    with open(tmp_path / "audit_log.jsonl") as f:
        lines = f.readlines()
    assert [json.loads(line)["run"] for line in lines] == ["a", "b"]


# ---------------------------------------------------------------- observability
def test_run_report_ok_when_clean(data):
    recon = governance.reconcile_balances(data["gold"], data["silver"])
    report = governance.run_report(data["silver"], data["gold"], recon)
    assert report["status"] == "OK"
    assert report["alerts"] == []
    assert report["quarantined_rows"] == len(data["silver"]["quarantine"])
    assert report["gold_accounts"] == 120


def test_run_report_alerts_on_high_quarantine(data):
    recon = governance.reconcile_balances(data["gold"], data["silver"])
    report = governance.run_report(data["silver"], data["gold"], recon,
                                   quarantine_rate_threshold=0.001)
    assert report["status"] == "FAILED"
    assert any("quarantine_rate" in a for a in report["alerts"])


# ---------------------------------------------------------------- anomalies
def test_anomaly_flags_extreme_contribution():
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(6)],
        "account_id": ["ACC-1"] * 6,
        "event_type": ["contribution"] * 6,
        "amount": [100.0, 105.0, 98.0, 102.0, 101.0, 5000.0],
        "event_date": pd.to_datetime(["2026-01-01"] * 6),
        "source": ["batch-file"] * 6,
        "ingested_at": pd.Timestamp("2026-11-28"),
    })
    flagged = governance.flag_anomalies(events)
    assert len(flagged) == 1
    assert flagged.iloc[0]["amount"] == 5000.0


def test_anomaly_ignores_normal_contributions(data):
    flagged = governance.flag_anomalies(data["silver"]["events"])
    # Seeded normal data: a small number of flags at most, never half the file.
    assert len(flagged) < 0.05 * (data["silver"]["events"]["event_type"]
                                 == "contribution").sum()


# ---------------------------------------------------------------- governance
def test_pii_access_restricted():
    assert governance.check_access("analyst", "holder_id") is False
    assert governance.check_access("auditor", "holder_id") is True
    assert governance.check_access("data-engineer", "holder_id") is True
    assert governance.check_access("analyst", "amount") is True


def test_control_checklist_all_satisfied():
    controls = governance.control_checklist()
    assert len(controls) == 5
    assert all(c["satisfied"] for c in controls)
