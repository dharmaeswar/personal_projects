"""Tests for positions and P&L (average-cost method)."""

from posttrade.enrichment import enrich_all
from posttrade.models import Execution
from posttrade.pnl import compute_pnl, total_pnl
from posttrade.positions import build_positions

SYMBOL = "AAPL 260117C00250000"


def _trades(specs):
    execs = [
        Execution(f"E{i+1}", SYMBOL, side, qty, price, "2026-11-24", "CBOE", "ACC-001")
        for i, (side, qty, price) in enumerate(specs)
    ]
    return enrich_all(execs)


def test_position_averages_cost_on_adds():
    positions = build_positions(_trades([("BUY", 10, 4.20), ("BUY", 10, 4.60)]))
    assert len(positions) == 1
    assert positions[0].net_quantity == 20
    assert positions[0].average_cost == 4.40
    assert positions[0].multiplier == 100


def test_position_keeps_cost_on_reduction():
    positions = build_positions(_trades([("BUY", 10, 4.20), ("SELL", 4, 4.50)]))
    assert positions[0].net_quantity == 6
    assert positions[0].average_cost == 4.20


def test_flat_position_disappears():
    assert build_positions(_trades([("BUY", 10, 4.20), ("SELL", 10, 4.50)])) == []


def test_short_position_has_negative_quantity():
    positions = build_positions(_trades([("SELL", 5, 4.20)]))
    assert positions[0].net_quantity == -5
    assert positions[0].average_cost == 4.20


def test_realised_pnl_on_long_reduction():
    # Sell 4 at 4.50 against avg cost 4.20: (4.50 - 4.20) * 4 * 100 = 120.
    rows = compute_pnl(_trades([("BUY", 10, 4.20), ("SELL", 4, 4.50)]), {SYMBOL: 4.60})
    assert rows[0].realised == 120.00
    assert rows[0].unrealised == 240.00  # (4.60 - 4.20) * 6 * 100
    assert rows[0].net_quantity == 6


def test_realised_pnl_on_short_cover():
    # Cover 5 short at 4.00 against avg cost 4.20: (4.20 - 4.00) * 5 * 100 = 100.
    rows = compute_pnl(_trades([("SELL", 5, 4.20), ("BUY", 5, 4.00)]), {SYMBOL: 4.10})
    assert rows[0].realised == 100.00
    assert rows[0].net_quantity == 0
    assert rows[0].unrealised == 0.00


def test_unrealised_loss_when_mark_below_cost():
    rows = compute_pnl(_trades([("BUY", 5, 12.30)]), {SYMBOL: 12.00})
    assert rows[0].realised == 0.00
    assert rows[0].unrealised == -150.00  # (12.00 - 12.30) * 5 * 100


def test_position_flip_opens_new_position_at_trade_price():
    rows = compute_pnl(_trades([("BUY", 4, 4.20), ("SELL", 10, 4.50)]), {SYMBOL: 4.60})
    assert rows[0].realised == 120.00  # (4.50 - 4.20) * 4 * 100
    assert rows[0].net_quantity == -6
    assert rows[0].unrealised == -60.00  # (4.60 - 4.50) * -6 * 100


def test_missing_mark_gives_zero_unrealised():
    rows = compute_pnl(_trades([("BUY", 10, 4.20)]), {})
    assert rows[0].unrealised == 0.00
    assert rows[0].realised == 0.00


def test_total_pnl_sums_rows():
    rows = compute_pnl(_trades([("BUY", 10, 4.20), ("SELL", 4, 4.50)]), {SYMBOL: 4.60})
    assert total_pnl(rows) == (120.00, 240.00, 360.00)


def test_total_pnl_empty_is_zero():
    assert total_pnl([]) == (0.0, 0.0, 0.0)
