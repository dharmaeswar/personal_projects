from datetime import date
from decimal import Decimal

from exports_etl import warehouse


def _rows():
    return [
        {
            "shipment_id": "EXP-1",
            "ship_date": date(2026, 11, 2),
            "origin": "US",
            "dest_country": "DE",
            "hs_code": "8471.30",
            "value_usd": Decimal("12500.00"),
            "weight_kg": Decimal("420.5"),
            "customs_status": "CLEARED",
        },
        {
            "shipment_id": "EXP-2",
            "ship_date": date(2026, 11, 2),
            "origin": "US",
            "dest_country": "JP",
            "hs_code": "8517.12",
            "value_usd": Decimal("8856.00"),
            "weight_kg": Decimal("310.0"),
            "customs_status": "DELIVERED",
        },
    ]


def test_load_inserts_facts_and_dims(tmp_path):
    conn = warehouse.connect(str(tmp_path / "w.db"))
    assert warehouse.load_rows(conn, _rows()) == 2
    assert conn.execute("SELECT COUNT(*) FROM fact_exports").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM dim_country").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM dim_product").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0] == 1
    assert warehouse.get_watermark(conn) == "2026-11-02"
    conn.close()


def test_load_is_idempotent(tmp_path):
    conn = warehouse.connect(str(tmp_path / "w.db"))
    assert warehouse.load_rows(conn, _rows()) == 2
    assert warehouse.load_rows(conn, _rows()) == 0  # re-run loads nothing twice
    assert conn.execute("SELECT COUNT(*) FROM fact_exports").fetchone()[0] == 2
    conn.close()


def test_watermark_only_advances(tmp_path):
    conn = warehouse.connect(str(tmp_path / "w.db"))
    warehouse.load_rows(conn, _rows())
    older = [dict(_rows()[0], shipment_id="EXP-9", ship_date=date(2026, 10, 1))]
    warehouse.load_rows(conn, older)
    assert warehouse.get_watermark(conn) == "2026-11-02"
    conn.close()


def test_monthly_value_by_country(tmp_path):
    conn = warehouse.connect(str(tmp_path / "w.db"))
    warehouse.load_rows(conn, _rows())
    result = dict(warehouse.monthly_value_by_country(conn, 2026, 11))
    assert result == {"DE": 12500.0, "JP": 8856.0}
    assert warehouse.monthly_value_by_country(conn, 2026, 10) == []
    conn.close()


def test_top_products(tmp_path):
    conn = warehouse.connect(str(tmp_path / "w.db"))
    warehouse.load_rows(conn, _rows())
    top = warehouse.top_products(conn, limit=1)
    assert top[0][0] == "8471.30"
    assert top[0][1] == 12500.0
    conn.close()


def test_total_value_usd(tmp_path):
    conn = warehouse.connect(str(tmp_path / "w.db"))
    assert warehouse.total_value_usd(conn) == 0.0
    warehouse.load_rows(conn, _rows())
    assert warehouse.total_value_usd(conn) == 21356.0
    conn.close()
