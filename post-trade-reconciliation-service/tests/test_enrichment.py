"""Tests for trade enrichment."""

from posttrade.enrichment import REFERENCE_DATA, enrich, enrich_all
from posttrade.models import Execution


def _exec(symbol="AAPL 260117C00250000", **over):
    kwargs = dict(
        exec_id="E1",
        symbol=symbol,
        side="BUY",
        quantity=10,
        price=4.20,
        trade_date="2026-11-24",
        venue="CBOE",
        account="ACC-001",
    )
    kwargs.update(over)
    return Execution(**kwargs)


def test_enrich_known_option_fills_reference_fields():
    trade = enrich(_exec())
    assert trade.enriched is True
    assert trade.instrument.underlying == "AAPL"
    assert trade.instrument.option_type == "CALL"
    assert trade.instrument.expiry == "2026-01-17"
    assert trade.instrument.strike == 250.00
    assert trade.instrument.multiplier == 100
    assert trade.instrument.currency == "USD"


def test_enrich_notionals_use_multiplier():
    trade = enrich(_exec(quantity=10, price=4.20))
    assert trade.notional == 10 * 4.20 * 100


def test_enrich_equity_multiplier_is_one():
    trade = enrich(_exec(symbol="AAPL", quantity=100, price=250.00, venue="NASDAQ"))
    assert trade.enriched is True
    assert trade.notional == 100 * 250.00 * 1


def test_enrich_unknown_symbol_is_flagged_not_dropped():
    trade = enrich(_exec(symbol="XYZ 260117C00010000", quantity=3, price=1.00))
    assert trade.enriched is False
    assert trade.instrument is None
    assert trade.notional == 3 * 1.00
    assert any("unknown instrument" in n for n in trade.enrichment_notes)


def test_enrich_venue_mismatch_is_noted():
    trade = enrich(_exec(venue="NYSE ARCA"))
    assert trade.enriched is True
    assert any("differs from listing exchange" in n for n in trade.enrichment_notes)


def test_enrich_all_preserves_order():
    trades = enrich_all([_exec(exec_id="E1"), _exec(exec_id="E2", symbol="AAPL")])
    assert [t.execution.exec_id for t in trades] == ["E1", "E2"]
    assert all(t.enriched for t in trades)


def test_reference_data_covers_demo_symbols():
    for symbol in (
        "AAPL 260117C00250000",
        "SPX 260117P00590000",
        "MSFT 260117C00420000",
        "AAPL",
    ):
        assert symbol in REFERENCE_DATA
