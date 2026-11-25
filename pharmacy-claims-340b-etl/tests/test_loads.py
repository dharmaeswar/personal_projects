"""Tests for end-to-end orchestration and reconciliation."""

from pathlib import Path

from claims_etl.loads import run_load

DATA = Path(__file__).resolve().parent.parent / "data"


def test_full_then_incremental_then_rerun(tmp_path):
    db = tmp_path / "wh.sqlite"
    full = run_load(DATA, db, mode="full")
    assert full["source_rows"] == 12
    assert full["loaded_rows"] == 5
    assert full["quarantined_rows"] == 7
    assert full["fact_rows"] == 5
    assert full["watermark"] == "2026-11-23"
    assert full["reconciled"] is True
    assert {q["claim_id"] for q in full["quarantine"]} == {
        "C1004", "C1005", "C1001", "C1007", "C1008", "C1011", "C1012"}

    inc = run_load(DATA, db, mode="incremental",
                   claims_file="claims_batch2.csv")
    assert inc["loaded_rows"] == 2
    assert inc["fact_rows"] == 7
    assert inc["reconciled"] is True

    rerun = run_load(DATA, db, mode="incremental",
                     claims_file="claims_batch2.csv")
    assert rerun["loaded_rows"] == 0
    assert rerun["skipped_already_loaded"] == 2
    assert rerun["fact_rows"] == 7
    assert rerun["reconciled"] is True
