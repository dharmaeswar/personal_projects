"""Tests for the Commissioning Data ETL Platform."""

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from commissioning_etl.api_client import PagedApiClient, TransientApiError, make_clients
from commissioning_etl.dashboards import daily_report, open_defects, system_progress, ticket_aging
from commissioning_etl.etl import init_db, load, run_pipeline, transform_systems, transform_tickets
from commissioning_etl.quality import run_checks

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.fixture
def clients():
    return make_clients(DATA)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    conn = init_db(path)
    yield conn, path
    conn.close()


def _loaded_db(tmp_path, clients):
    path = str(tmp_path / "test.db")
    run_pipeline(clients, path)
    return sqlite3.connect(path), path


# --- API client ---

def test_pagination_walks_all_pages(clients):
    systems = clients["systems"].fetch_all()
    assert len(systems) == 13
    tickets = clients["tickets"].fetch_all()
    assert len(tickets) == 26


def test_page_beyond_end_is_empty(clients):
    result = clients["systems"].list_page(99)
    assert result["items"] == []


def test_transient_failure_retried(clients):
    flaky = PagedApiClient(os.path.join(DATA, "commissioning_systems.json"),
                           fail_first_page_once=True)
    with pytest.raises(TransientApiError):
        flaky.list_page(1)
    items = flaky.fetch_all()
    assert len(items) == 13


# --- Transform ---

def test_duplicate_system_keeps_newest(clients):
    raw = clients["systems"].fetch_all()
    valid, quarantined, dups = transform_systems(raw)
    assert dups == 1
    elec2 = [s for s in valid if s["system_id"] == "SYS-ELEC-02"][0]
    assert elec2["completed_checkpoints"] == 22  # newer re-delivery wins
    assert elec2["updated_at"] == "2026-11-26"


def test_invalid_system_quarantined_with_reason(clients):
    raw = clients["systems"].fetch_all()
    valid, quarantined, _ = transform_systems(raw)
    assert len(valid) == 11
    assert len(quarantined) == 1
    assert quarantined[0][0] == "SYS-MECH-03"
    assert "exceed" in quarantined[0][1]


def test_ticket_validation_quarantines_bad_rows(clients):
    raw = clients["tickets"].fetch_all()
    valid, quarantined, dups = transform_tickets(
        raw, {"SYS-ELEC-01", "SYS-MECH-01", "SYS-HVAC-01"})
    assert dups == 1
    reasons = {q[0]: q[1] for q in quarantined}
    assert "missing or unknown priority" in reasons.get("TKT-124", "")
    assert "unknown system_id" in reasons.get("TKT-125", "")


# --- Full pipeline ---

def test_full_run_counts(tmp_path, clients):
    summary = run_pipeline(clients, str(tmp_path / "test.db"))
    assert summary == {
        "systems_received": 13, "systems_loaded": 11,
        "systems_duplicates": 1, "systems_quarantined": 1,
        "tickets_received": 26, "tickets_loaded": 23,
        "tickets_duplicates": 1, "tickets_quarantined": 2,
    }


def test_rerun_is_incremental(tmp_path, clients):
    path = str(tmp_path / "test.db")
    run_pipeline(clients, path)
    conn = sqlite3.connect(path)
    before = conn.execute("SELECT COUNT(*) FROM bronze_systems").fetchone()[0]
    conn.close()
    run_pipeline(clients, path)
    conn = sqlite3.connect(path)
    after = conn.execute("SELECT COUNT(*) FROM bronze_systems").fetchone()[0]
    assert before == after == 11
    conn.close()


def test_quarantine_rows_never_loaded(tmp_path, clients):
    conn, _ = _loaded_db(tmp_path, clients)
    assert conn.execute(
        "SELECT COUNT(*) FROM bronze_systems WHERE system_id='SYS-MECH-03'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM bronze_tickets WHERE ticket_id IN ('TKT-124','TKT-125')"
    ).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0] == 3
    conn.close()


# --- Quality ---

def test_all_quality_checks_pass_on_seed(tmp_path, clients):
    conn, _ = _loaded_db(tmp_path, clients)
    checks = run_checks(conn)
    assert len(checks) == 11
    assert all(c["status"] == "pass" for c in checks), checks
    conn.close()


def test_quality_catches_broken_invariant(db):
    conn, _ = db
    conn.execute(
        "INSERT INTO bronze_systems VALUES ('SYS-BAD','Electrical','Bad',10,12,'2026-11-26')"
    )
    conn.execute(
        "INSERT INTO mart_ticket_aging VALUES ('TKT-1','SYS-BAD','x','Open','P1',1,0)"
    )
    conn.commit()
    checks = {c["name"]: c["status"] for c in run_checks(conn)}
    assert checks["checkpoint_invariant"] == "fail"


def test_quality_catches_orphan_ticket(db):
    conn, _ = db
    conn.execute(
        "INSERT INTO bronze_tickets VALUES ('TKT-9','SYS-NOPE','x','Open','P2',"
        "'2026-11-20','2026-11-26')"
    )
    conn.execute(
        "INSERT INTO mart_ticket_aging VALUES ('TKT-9','SYS-NOPE','x','Open','P2',7,0)"
    )
    conn.commit()
    checks = {c["name"]: c["status"] for c in run_checks(conn)}
    assert checks["ticket_system_references"] == "fail"


# --- Dashboards ---

def test_progress_totals(tmp_path, clients):
    conn, _ = _loaded_db(tmp_path, clients)
    prog = system_progress(conn)
    assert len(prog["systems"]) == 11
    total = sum(r[2] for r in prog["areas"])
    done = sum(r[3] for r in prog["areas"])
    assert (total, done) == (280, 197)
    assert round(100.0 * done / total, 1) == 70.4
    conn.close()


def test_ticket_aging_and_sla(tmp_path, clients):
    conn, _ = _loaded_db(tmp_path, clients)
    defects = open_defects(conn)
    assert len(defects) == 15  # Open + In Progress
    breaches = [d for d in defects if d[5] > 30]
    assert len(breaches) == 3
    assert {d[0] for d in breaches} == {"TKT-101", "TKT-104", "TKT-113"}
    buckets = ticket_aging(conn)
    assert sum(r[2] for r in buckets) == 15
    conn.close()


def test_daily_report_contents(tmp_path, clients):
    conn, _ = _loaded_db(tmp_path, clients)
    report = daily_report(conn)
    assert "197/280" in report
    assert "70.4%" in report
    assert "past 30-day SLA: 3" in report
    conn.close()


def test_run_pipeline_script(tmp_path):
    import subprocess
    out = subprocess.run(
        [sys.executable, "run_pipeline.py"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "Quality checks: 11/11 passed" in out.stdout
