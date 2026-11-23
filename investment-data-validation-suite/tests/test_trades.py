"""Tests for trade-data validations."""

from investment_data_validation.data import (
    AS_OF,
    build_security_master,
    build_trades,
)
from investment_data_validation.trades import validate_trades


def _setup():
    securities = build_security_master()
    ids = {s["security_id"] for s in securities}
    return securities, ids


def _findings(report, check, record_id):
    return [f for f in report.findings
            if f.check == check and f.record_id == record_id]


def test_clean_trades_pass():
    securities, ids = _setup()
    report = validate_trades(build_trades(securities)[:55], ids, AS_OF)
    assert report.failed == 0
    assert report.records_checked == 55


def test_settlement_before_trade_flagged():
    securities, ids = _setup()
    report = validate_trades(build_trades(securities), ids, AS_OF)
    assert _findings(report, "settlement_after_trade", "TRD-9901")


def test_duplicate_trade_id_flagged():
    securities, ids = _setup()
    report = validate_trades(build_trades(securities), ids, AS_OF)
    assert [f for f in report.findings if f.check == "unique_trade_id"]


def test_unknown_security_flagged():
    securities, ids = _setup()
    report = validate_trades(build_trades(securities), ids, AS_OF)
    assert _findings(report, "security_exists", "TRD-9903")


def test_zero_quantity_and_negative_price_flagged():
    securities, ids = _setup()
    report = validate_trades(build_trades(securities), ids, AS_OF)
    assert _findings(report, "quantity_positive", "TRD-9904")
    assert _findings(report, "price_positive", "TRD-9904")


def test_future_trade_flagged():
    securities, ids = _setup()
    report = validate_trades(build_trades(securities), ids, AS_OF)
    assert _findings(report, "trade_not_future", "TRD-9905")


def test_bad_side_flagged():
    securities, ids = _setup()
    row = dict(build_trades(securities)[0])
    row["trade_id"] = "TRD-TEST"
    row["side"] = "HOLD"
    report = validate_trades([row], ids, AS_OF)
    assert _findings(report, "side_valid", "TRD-TEST")
