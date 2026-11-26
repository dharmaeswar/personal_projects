"""End-to-end tests for the monthly pipeline run."""

import json
import sqlite3

from fabric_hedis.pipeline import run_monthly


def test_full_monthly_run(tmp_path):
    work = tmp_path / "work"
    summary = run_monthly(work, "2026-10")
    assert summary["silver"]["bronze_claims"] == 186
    assert summary["silver"]["silver_claims"] == 179
    assert summary["silver"]["quarantined"] == 6
    assert summary["silver"]["duplicates_removed"] == 1
    assert summary["vendor"] == {
        "vendor_file": str(work / "sftp" / "outbound"
                           / "hedis_monthly_2026-10.csv"),
        "accepted": 4, "rejected": 0}
    assert summary["reconciliation"][0] is True
    assert summary["alerts"] == []
    assert (work / "hedis_report.json").exists()
    assert (work / "hedis_report.txt").exists()
    assert (work / "powerbi_semantic_model.json").exists()
    report = json.loads((work / "hedis_report.json").read_text())
    assert report["silver_claims"] == 179
    assert len(report["hedis"]) == 4
    conn = sqlite3.connect(work / "fabric_warehouse.db")
    gold = conn.execute(
        "SELECT COUNT(*) FROM gold_hedis_monthly").fetchone()[0]
    assert gold == 4
    runs = conn.execute(
        "SELECT COUNT(DISTINCT step) FROM run_log").fetchone()[0]
    assert runs >= 8  # every step recorded


def test_rerun_is_idempotent(tmp_path):
    work = tmp_path / "work"
    first = run_monthly(work, "2026-10")
    second = run_monthly(work, "2026-10")
    assert first["hedis"] == second["hedis"]
    assert first["silver"] == second["silver"]
    conn = sqlite3.connect(work / "fabric_warehouse.db")
    gold = conn.execute(
        "SELECT COUNT(*) FROM gold_hedis_monthly").fetchone()[0]
    assert gold == 4  # replaced, not duplicated
