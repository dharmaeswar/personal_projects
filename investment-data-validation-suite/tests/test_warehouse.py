"""Tests for legacy-to-warehouse reconciliation."""

from investment_data_validation.data import (
    build_security_master,
    build_warehouse_snapshots,
)
from investment_data_validation.warehouse import reconcile_warehouse


def _findings(report, check, record_id):
    return [f for f in report.findings
            if f.check == check and f.record_id == record_id]


def test_identical_snapshots_are_clean():
    securities = build_security_master()
    legacy, _ = build_warehouse_snapshots(securities)
    report = reconcile_warehouse(legacy, [dict(r) for r in legacy])
    assert report.failed == 0


def test_missing_key_flagged():
    securities = build_security_master()
    legacy, warehouse = build_warehouse_snapshots(securities)
    report = reconcile_warehouse(legacy, warehouse)
    assert _findings(report, "key_in_warehouse", "SEC-1005")


def test_orphan_key_flagged():
    securities = build_security_master()
    legacy, warehouse = build_warehouse_snapshots(securities)
    report = reconcile_warehouse(legacy, warehouse)
    assert _findings(report, "key_in_legacy", "SEC-8888")


def test_value_mismatch_flagged():
    securities = build_security_master()
    legacy, warehouse = build_warehouse_snapshots(securities)
    report = reconcile_warehouse(legacy, warehouse)
    assert _findings(report, "value_match", "SEC-1010")


def test_row_count_mismatch_flagged():
    securities = build_security_master()
    legacy, _ = build_warehouse_snapshots(securities)
    report = reconcile_warehouse(legacy, legacy[:10])
    assert _findings(report, "row_count_match", "ALL")
