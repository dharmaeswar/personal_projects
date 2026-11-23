from datetime import date

from exports_etl import quality

RATES = {"USD": 1, "EUR": 1.08}
TODAY = date(2026, 11, 23)


def _row(**overrides):
    row = {
        "shipment_id": "EXP-1",
        "ship_date": date(2026, 11, 2),
        "origin": "US",
        "dest_country": "DE",
        "hs_code": "8471.30",
        "value": 100,
        "currency": "USD",
        "weight_kg": 10,
        "customs_status": "CLEARED",
    }
    row.update(overrides)
    return row


def test_clean_row_has_no_reasons():
    assert quality.validate_row(_row(), set(), RATES, today=TODAY) == []


def test_duplicate_shipment_id():
    assert "duplicate_shipment_id" in quality.validate_row(
        _row(), {"EXP-1"}, RATES, today=TODAY
    )


def test_future_ship_date():
    assert "future_ship_date" in quality.validate_row(
        _row(ship_date=date(2026, 12, 1)), set(), RATES, today=TODAY
    )


def test_bad_hs_code():
    assert "bad_hs_code" in quality.validate_row(
        _row(hs_code="ABC"), set(), RATES, today=TODAY
    )
    assert "bad_hs_code" in quality.validate_row(
        _row(hs_code="847130"), set(), RATES, today=TODAY
    )


def test_non_positive_value_and_weight():
    reasons = quality.validate_row(
        _row(value=0, weight_kg=-1), set(), RATES, today=TODAY
    )
    assert "non_positive_value" in reasons
    assert "non_positive_weight" in reasons


def test_unknown_currency_and_status():
    reasons = quality.validate_row(
        _row(currency="BRL", customs_status="LOST"), set(), RATES, today=TODAY
    )
    assert "unknown_currency" in reasons
    assert "bad_customs_status" in reasons


def test_split_valid_quarantines_and_keeps_rest():
    rows = [_row(), _row(shipment_id="EXP-1"), _row(shipment_id="EXP-2", value=-5)]
    valid, quarantined = quality.split_valid(rows, RATES, today=TODAY)
    assert [r["shipment_id"] for r in valid] == ["EXP-1"]
    assert len(quarantined) == 2
    assert quarantined[0]["reasons"] == ["duplicate_shipment_id"]
    assert "non_positive_value" in quarantined[1]["reasons"]
