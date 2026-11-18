from conftest import make_line
from src.contracts import validate_line


def test_valid_line_passes():
    assert validate_line(make_line()) == []


def test_missing_field():
    line = make_line()
    del line["account"]
    assert any("missing field: account" in e for e in validate_line(line))


def test_unknown_account_rejected():
    assert any("unknown account" in e for e in validate_line(make_line(account="9999")))


def test_both_sides_set_rejected():
    assert any("both debit and credit" in e for e in validate_line(make_line(debit=500, credit=500)))


def test_zero_amount_rejected():
    assert any("zero-amount" in e for e in validate_line(make_line(debit=0, credit=0)))


def test_negative_amount_rejected():
    assert any("negative amount" in e for e in validate_line(make_line(debit=-100)))


def test_date_period_mismatch_rejected():
    assert any("does not match fiscal_period" in e for e in validate_line(make_line(posting_date="2026-09-30")))


def test_non_usd_rejected():
    assert any("unsupported currency" in e for e in validate_line(make_line(currency="EUR")))
