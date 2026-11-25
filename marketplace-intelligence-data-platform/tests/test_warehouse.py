"""Tests for the warehouse: SCD2 zone history, idempotent incremental
loads, watermark behaviour, and backfill."""

import pytest

from marketintel import warehouse


@pytest.fixture
def conn(tmp_path):
    c = warehouse.connect(str(tmp_path / "test.sqlite"))
    yield c
    c.close()


def test_scd2_zone_rename_closes_old_row(conn):
    key1 = warehouse.upsert_zone(conn, "downtown", "Sunnyvale", "2026-11-24")
    key2 = warehouse.upsert_zone(conn, "downtown", "Sunnyvale", "2026-11-24")
    assert key1 == key2  # same city: no new row
    key3 = warehouse.upsert_zone(conn, "downtown", "Mountain View", "2026-11-25")
    assert key3 != key1
    old = conn.execute(
        "SELECT current, valid_to FROM dim_zone WHERE zone_key = ?", (key1,)
    ).fetchone()
    assert old == (0, "2026-11-25")
    current = conn.execute(
        "SELECT COUNT(*) FROM dim_zone WHERE zone = 'downtown' AND current = 1"
    ).fetchone()[0]
    assert current == 1


def _row(**kw):
    base = {"competitor": "lyft", "zone": "downtown",
            "snapshot_date": "2026-11-24", "source": "feed",
            "price_usd": 17.25, "service": "ride"}
    base.update(kw)
    return base


def test_load_is_idempotent(conn):
    rows = [_row(), _row(zone="airport", price_usd=30.5)]
    assert warehouse.load_rows(conn, rows) == (2, 0)
    assert warehouse.load_rows(conn, rows) == (0, 2)
    assert warehouse.fact_count(conn) == 2


def test_watermark_skips_old_rows(conn):
    assert warehouse.load_rows(conn, [_row()]) == (1, 0)
    assert warehouse.get_watermark(conn) == "2026-11-24"
    # Same date again is skipped as already loaded.
    assert warehouse.load_rows(conn, [_row(zone="airport")]) == (0, 1)


def test_backfill_loads_old_rows(conn):
    warehouse.load_rows(conn, [_row(snapshot_date="2026-11-25")])
    old = _row(snapshot_date="2026-11-24", zone="airport")
    assert warehouse.load_rows(conn, [old]) == (0, 1)
    assert warehouse.load_rows(conn, [old], backfill=True) == (1, 0)
    assert warehouse.fact_count(conn) == 2


def test_daily_average_price(conn):
    warehouse.load_rows(conn, [_row(), _row(price_usd=20.75)])
    # Second row has the same natural key: deduped, so one fact row.
    assert warehouse.fact_count(conn) == 1
    warehouse.load_rows(conn, [_row(snapshot_date="2026-11-25", price_usd=18.90)],
                        backfill=True)
    avgs = warehouse.daily_average_price(conn)
    assert avgs[0][:3] == ("downtown", "2026-11-24", 17.25)
    assert avgs[1][:3] == ("downtown", "2026-11-25", 18.9)
