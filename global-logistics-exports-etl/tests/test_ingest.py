from datetime import date
from decimal import Decimal

from exports_etl import ingest


def test_read_manifests_parses_types(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text(
        "shipment_id,ship_date,origin,dest_country,hs_code,value,currency,weight_kg,customs_status\n"
        "EXP-1,2026-11-02,US,DE,8471.30,12500.00,USD,420.5,CLEARED\n"
    )
    rows = ingest.read_manifests(str(path))
    assert len(rows) == 1
    row = rows[0]
    assert row["shipment_id"] == "EXP-1"
    assert row["ship_date"] == date(2026, 11, 2)
    assert row["value"] == Decimal("12500.00")
    assert row["weight_kg"] == Decimal("420.5")
    assert row["dest_country"] == "DE"
    assert row["currency"] == "USD"


def test_read_manifests_bad_values_become_none(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text(
        "shipment_id,ship_date,origin,dest_country,hs_code,value,currency,weight_kg,customs_status\n"
        "EXP-2,not-a-date,US,,bad-code,abc,USD,xyz,BOGUS\n"
    )
    row = ingest.read_manifests(str(path))[0]
    assert row["ship_date"] is None
    assert row["value"] is None
    assert row["weight_kg"] is None
    assert row["dest_country"] == ""


def test_read_rates_skips_bad_rows(tmp_path):
    path = tmp_path / "r.csv"
    path.write_text("currency,rate_to_usd\nUSD,1.00\nEUR,1.08\nXXX,not-a-rate\nYYY,-2\n")
    rates = ingest.read_rates(str(path))
    assert rates == {"USD": Decimal("1.00"), "EUR": Decimal("1.08")}
