from decimal import Decimal

import pytest

from exports_etl import fx


def test_to_usd_converts_and_rounds():
    rates = {"EUR": Decimal("1.08"), "USD": Decimal("1")}
    assert fx.to_usd(Decimal("100.00"), "EUR", rates) == Decimal("108.00")
    assert fx.to_usd(Decimal("100.00"), "USD", rates) == Decimal("100.00")


def test_to_usd_unknown_currency_raises():
    with pytest.raises(KeyError):
        fx.to_usd(Decimal("10"), "BRL", {"USD": Decimal("1")})


def test_convert_row_adds_value_usd():
    row = {"value": Decimal("50.00"), "currency": "EUR"}
    converted = fx.convert_row(row, {"EUR": Decimal("1.08")})
    assert converted["value_usd"] == Decimal("54.00")
    assert converted["value"] == Decimal("50.00")  # original untouched
