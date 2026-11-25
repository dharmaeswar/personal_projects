"""Tests for warehouse loads: full refresh and watermark incremental."""

from claims_etl import warehouse

CLAIMS = [
    {"claim_id": "C1", "patient_id": "P1", "ndc": "00000000001",
     "quantity": 30, "days_supply": 30, "fill_date": "2026-11-20",
     "pharmacy_id": "PH01", "prescriber_id": "DR01", "amount": 45.00},
    {"claim_id": "C2", "patient_id": "P1", "ndc": "00000000001",
     "quantity": 30, "days_supply": 30, "fill_date": "2026-11-21",
     "pharmacy_id": "PH01", "prescriber_id": "DR01", "amount": 45.00},
]


def test_full_load_replaces_fact_table():
    conn = warehouse.connect(":memory:")
    assert warehouse.load_full(conn, CLAIMS, 1) == 2
    assert warehouse.fact_count(conn) == 2
    assert warehouse.load_full(conn, CLAIMS[:1], 2) == 1
    assert warehouse.fact_count(conn) == 1


def test_incremental_load_uses_watermark_and_is_idempotent():
    conn = warehouse.connect(":memory:")
    inserted, watermark = warehouse.load_incremental(conn, CLAIMS, None, 1)
    assert (inserted, watermark) == (2, "2026-11-21")
    # Same batch again: nothing new after the watermark.
    inserted, watermark = warehouse.load_incremental(
        conn, CLAIMS, watermark, 2)
    assert inserted == 0
    assert warehouse.fact_count(conn) == 2
    # A later claim loads; an older one does not.
    later = [dict(CLAIMS[0], claim_id="C3", fill_date="2026-11-22")]
    inserted, watermark = warehouse.load_incremental(
        conn, later, "2026-11-21", 3)
    assert (inserted, watermark) == (1, "2026-11-22")


def test_load_log_and_watermark_round_trip():
    conn = warehouse.connect(":memory:")
    load_id = warehouse.log_load(conn, "full", 12, 5, 7, "2026-11-23")
    assert load_id == 1
    assert warehouse.latest_watermark(conn) == "2026-11-23"
