import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client_analytics import data, ingest, validate


def fresh_conn(tmp_path):
    conn = ingest.open_db(str(tmp_path / "test.db"))
    ingest.load(conn, data.generate())
    return conn


def test_counts(tmp_path):
    conn = fresh_conn(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 60
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 601
    assert conn.execute("SELECT COUNT(*) FROM ops_events").fetchone()[0] == 120


def test_planted_faults_are_caught(tmp_path):
    conn = fresh_conn(tmp_path)
    valid, exceptions = validate.validate_transactions(conn)
    checks = sorted(e["check"] for e in exceptions)
    assert "negative_amount" in checks
    assert "missing_amount" in checks
    assert "duplicate_txn_id" in checks
    assert "orphan_account" in checks
    # Seeded data: 3 planted bad transactions + 5 transactions that
    # landed on the orphan account = 8 bad rows, 593 valid.
    assert len(exceptions) == 8
    assert len(valid) == 593
    # No valid row has a bad amount or a duplicate id.
    assert all(v["amount"] is not None and v["amount"] >= 0 for v in valid)
    assert len({v["txn_id"] for v in valid}) == len(valid)


def test_orphan_account_caught(tmp_path):
    conn = fresh_conn(tmp_path)
    exceptions = validate.validate_accounts(conn)
    assert len(exceptions) == 1
    assert exceptions[0]["account_id"] == "ACC-0080"
    assert exceptions[0]["check"] == "orphan_account"


def test_reconciliation_matches(tmp_path):
    conn = fresh_conn(tmp_path)
    valid, _ = validate.validate_transactions(conn)
    assert validate.reconcile_python_vs_sql(conn, valid) == []
