"""Tests for the medallion layers: bronze -> silver -> reconcile."""

from fabric_hedis import medallion, seed
from fabric_hedis.sftp_exchange import receive_files


def _load(tmp_path):
    seed.write_inbound_files(tmp_path / "inbound")
    received = receive_files(tmp_path / "inbound")
    conn = medallion.connect(tmp_path / "fabric_warehouse.db")
    table_for = {
        "members_2026-10.csv": ("bronze_members", seed.MEMBER_COLUMNS),
        "claims_2026-10.csv": ("bronze_claims", seed.CLAIM_COLUMNS),
        "labs_2026-10.csv": ("bronze_labs", seed.LAB_COLUMNS),
        "screenings_2026-10.csv": ("bronze_screenings",
                                   seed.SCREENING_COLUMNS),
    }
    for filename, rows in received.items():
        table, columns = table_for[filename]
        medallion.load_bronze(conn, table, rows, columns)
    return conn


def test_promote_counts(tmp_path):
    conn = _load(tmp_path)
    stats = medallion.promote_to_silver(conn)
    # 186 bronze claims = 180 clean + 6 planted defects; one defect is a
    # late duplicate copy of C00001, so 1 duplicate removed, 6 quarantined.
    assert stats["bronze_claims"] == 186
    assert stats["duplicates_removed"] == 1
    assert stats["quarantined"] == 6
    assert stats["silver_claims"] == 179
    assert stats["silver_members"] == 60
    assert stats["bronze_claims"] == (stats["silver_claims"]
                                      + stats["quarantined"]
                                      + stats["duplicates_removed"])


def test_quarantine_reasons_cover_all_six_defects(tmp_path):
    conn = _load(tmp_path)
    medallion.promote_to_silver(conn)
    reasons = {r[0]: r[1] for r in conn.execute(
        "SELECT record_id, reason FROM quarantine").fetchall()}
    assert len(reasons) == 6
    assert "paid_amount_mismatch" in reasons["C00001"]
    assert "negative_paid_amount" in reasons["C99991"]
    assert "unknown_member_id" in reasons["C99992"]
    assert "service_date_out_of_range" in reasons["C99993"]
    assert "unknown_diag_code" in reasons["C99994"]
    assert "paid_amount_mismatch" in reasons["C99995"]


def test_reconcile_passes_after_save(tmp_path):
    conn = _load(tmp_path)
    stats = medallion.promote_to_silver(conn)
    medallion.save_run_stats(conn, "2026-10", stats)
    ok, detail = medallion.reconcile(conn, "2026-10")
    assert ok, detail
    assert "bronze=186 silver=179 quarantined=6 duplicates_removed=1" in detail


def test_reconcile_fails_without_stats(tmp_path):
    conn = medallion.connect(tmp_path / "db.sqlite")
    ok, detail = medallion.reconcile(conn, "2026-10")
    assert not ok
    assert "no run_stats" in detail


def test_silver_claims_are_unique_and_clean(tmp_path):
    conn = _load(tmp_path)
    medallion.promote_to_silver(conn)
    rows = conn.execute(
        "SELECT claim_id, paid_amount, billed_amount, adjustment"
        " FROM silver_claims").fetchall()
    assert len({r[0] for r in rows}) == len(rows) == 179
    assert all(r[1] >= 0 for r in rows)
    assert all(abs(r[1] - (r[2] - r[3])) <= 0.01 for r in rows)


def test_delta_log_records_every_write(tmp_path):
    conn = _load(tmp_path)
    medallion.promote_to_silver(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT DISTINCT table_name FROM delta_log").fetchall()}
    assert {"bronze_claims", "silver_claims", "silver_members"} <= tables
