"""Tests for the warehouse model: star schema, SCD2, watermark loads."""

from datetime import date

from homehealth import quality, warehouse

TODAY = date(2026, 11, 26)


def load_seed(conn):
    from homehealth import ingest
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent
    visits = ingest.read_visit_csv(base / "data" / "visits.csv")
    valid, quarantined = quality.validate_visits(visits.records, TODAY)
    return warehouse.load_visits(
        conn, valid, quarantined, "test-run",
        source_rows=len(visits.records), incremental=False,
    )


def test_seed_load_counts():
    conn = warehouse.connect()
    result = load_seed(conn)
    assert result["loaded"] == 12
    assert result["quarantined"] == 4
    assert result["fact_rows"] == 12
    assert result["reconciled"] is True


def test_quarantine_reasons_recorded():
    conn = warehouse.connect()
    load_seed(conn)
    rows = conn.execute(
        "SELECT reasons FROM quarantine ORDER BY quarantine_id"
    ).fetchall()
    reasons = " | ".join(row[0] for row in rows)
    assert "duplicate visit_id V001" in reasons
    assert "duration_min -30" in reasons
    assert "missing clinician_id" in reasons
    assert "in the future" in reasons


def test_reload_is_idempotent():
    conn = warehouse.connect()
    first = load_seed(conn)
    second = load_seed(conn)
    assert first["loaded"] == 12
    assert second["loaded"] == 0
    assert second["fact_rows"] == 12
    assert second["reconciled"] is True


def test_incremental_load_skips_watermarked_rows():
    conn = warehouse.connect()
    load_seed(conn)
    # New visit after the watermark (2026-11-20) loads; an old one skips.
    from homehealth import quality as q

    new_rows = [
        {
            "visit_id": "V020", "patient_key": "P011", "clinician_id": "C101",
            "visit_date": "2026-11-21", "duration_min": 40,
            "care_plan": "wound-care", "assessment_score": 80,
            "source": "visit_feed_csv", "schema_version": "v1",
        },
        {
            "visit_id": "V021", "patient_key": "P012", "clinician_id": "C101",
            "visit_date": "2026-11-10", "duration_min": 40,
            "care_plan": "wound-care", "assessment_score": 80,
            "source": "visit_feed_csv", "schema_version": "v1",
        },
    ]
    valid, quarantined = q.validate_visits(new_rows, TODAY)
    result = warehouse.load_visits(
        conn, valid, quarantined, "test-run-2",
        source_rows=len(new_rows), incremental=True,
    )
    assert result["loaded"] == 1
    assert result["skipped"] == 1
    assert result["fact_rows"] == 13


def test_care_plan_change_opens_new_scd2_row():
    conn = warehouse.connect()
    load_seed(conn)
    rows = conn.execute(
        "SELECT care_plan, is_current, valid_to FROM dim_patient "
        "WHERE patient_key = 'P001' ORDER BY patient_sk"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["care_plan"] == "wound-care"
    assert rows[0]["is_current"] == 0
    assert rows[0]["valid_to"] == "2026-11-18"
    assert rows[1]["care_plan"] == "wound-care-plus"
    assert rows[1]["is_current"] == 1


def test_summary_view_aggregates_from_fact():
    conn = warehouse.connect()
    load_seed(conn)
    rows = conn.execute(
        "SELECT * FROM v_visit_summary WHERE visit_date = '2026-11-10'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["visits"] == 2
    assert rows[0]["total_minutes"] == 105
