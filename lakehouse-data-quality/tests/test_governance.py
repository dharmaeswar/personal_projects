"""Tests for the governed-access module (lakehouse.governance)."""

import pandas as pd
import pytest

from lakehouse.data import generate_bronze
from lakehouse.governance import (
    decide_access,
    generate_access_requests,
    generate_grants,
    point_in_time_gold,
    reconcile_gold,
    run_governance,
)
from lakehouse.pipeline import build_gold, build_silver


@pytest.fixture(scope="module")
def built():
    bronze = generate_bronze()
    silver, quarantine = build_silver(
        bronze["orders"], bronze["customers"], bronze["products"]
    )
    gold = build_gold(silver, bronze["products"])
    return bronze, silver, quarantine, gold


def test_grants_and_requests_shapes():
    assert len(generate_grants()) == 5
    assert len(generate_access_requests()) == 8
    assert generate_grants()["grant_id"].is_unique
    assert generate_access_requests()["request_id"].is_unique


def test_matching_request_is_allowed():
    decisions, _ = decide_access(generate_grants(), generate_access_requests())
    by_id = decisions.set_index("request_id")["decision"].to_dict()
    assert by_id["R01"] == "allowed"  # full grant, reporting purpose
    assert by_id["R02"] == "allowed"  # finance grant, reconciliation purpose
    assert by_id["R03"] == "allowed"  # customer dim, region only
    assert by_id["R08"] == "allowed"  # external auditor, audit purpose


def test_no_grant_is_denied():
    decisions, _ = decide_access(generate_grants(), generate_access_requests())
    row = decisions[decisions["request_id"] == "R04"].iloc[0]
    assert row["decision"] == "denied"
    assert "no grant" in row["reason"]


def test_column_outside_grant_is_denied():
    decisions, _ = decide_access(generate_grants(), generate_access_requests())
    row = decisions[decisions["request_id"] == "R05"].iloc[0]
    assert row["decision"] == "denied"
    assert "customer_name" in row["reason"]


def test_expired_grant_is_denied():
    decisions, _ = decide_access(generate_grants(), generate_access_requests())
    row = decisions[decisions["request_id"] == "R06"].iloc[0]
    assert row["decision"] == "denied"
    assert "expired" in row["reason"]
    assert row["grant_id"] == "G04"


def test_purpose_outside_grant_is_denied():
    decisions, _ = decide_access(generate_grants(), generate_access_requests())
    row = decisions[decisions["request_id"] == "R07"].iloc[0]
    assert row["decision"] == "denied"
    assert "purpose" in row["reason"]


def test_audit_log_covers_every_request():
    _, audit_log = decide_access(generate_grants(), generate_access_requests())
    assert len(audit_log) == 8
    assert {e["request_id"] for e in audit_log} == {
        f"R0{i}" for i in range(1, 9)
    }
    assert all(e["decision"] in ("allowed", "denied") for e in audit_log)
    assert all(e["reason"] for e in audit_log)


def test_gold_reconciles_to_silver(built):
    _, silver, _, gold = built
    rec = reconcile_gold(gold, silver)
    assert rec["reconciled"] is True
    assert rec["difference"] == 0.0
    assert rec["silver_rows"] == len(silver)


def test_point_in_time_is_a_strict_subset(built):
    bronze, silver, _, gold = built
    pit = point_in_time_gold(silver, bronze["products"], pd.Timestamp("2026-06-30"))
    assert len(pit) < len(gold)
    assert float(pit["total_revenue"].sum()) < float(gold["total_revenue"].sum())
    rec = reconcile_gold(pit, silver[silver["order_date"] <= "2026-06-30"])
    assert rec["reconciled"] is True


def test_run_governance_summary_counts():
    summary = run_governance()
    assert summary["bronze_orders"] == 200
    assert summary["silver_rows"] == 187
    assert summary["quarantined_rows"] == 13
    assert summary["gold_groups"] == 185
    assert summary["grants"] == 5
    assert summary["requests"] == 8
    assert summary["allowed"] == 4
    assert summary["denied"] == 4
    assert summary["audit_entries"] == 8
    assert summary["reconciliation"]["reconciled"] is True
    assert summary["point_in_time_reconciled"] is True
    assert summary["point_in_time_groups"] < summary["gold_groups"]
