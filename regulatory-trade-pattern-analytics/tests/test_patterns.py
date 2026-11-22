import pandas as pd
import pytest

from trade_reg_analytics.data import WarehouseConfig, build_positions, generate_orders_trades
from trade_reg_analytics.patterns import (
    detect_marking_the_close,
    detect_position_concentration,
    detect_spoofing,
    detect_wash_trades,
    run_all_detectors,
)


@pytest.fixture(scope="module")
def frames():
    orders, trades = generate_orders_trades(WarehouseConfig(seed=42, days=5))
    positions = build_positions(trades)
    return orders, trades, positions


def test_wash_trade_finds_planted_account(frames):
    _, trades, _ = frames
    findings = detect_wash_trades(trades)
    assert not findings.empty
    planted = findings[(findings["account"] == "ACC-007") & (findings["instrument"] == "ES")]
    assert len(planted) == 5  # one per day
    assert (planted["matched_quantity"] >= 25).all()


def test_spoofing_finds_planted_cluster(frames):
    orders, _, _ = frames
    findings = detect_spoofing(orders)
    assert not findings.empty
    planted = findings[(findings["account"] == "ACC-019") & (findings["instrument"] == "CL")]
    assert len(planted) == 5
    assert (planted["orders_cancelled"] == 12).all()
    assert (planted["avg_cancel_seconds"] == 3.0).all()


def test_wash_trade_ignores_small_matches():
    trades = pd.DataFrame(
        {
            "trade_id": ["T1", "T2"],
            "account": ["A", "A"],
            "instrument": ["ES", "ES"],
            "trade_date": ["2026-01-05"] * 2,
            "side": ["BUY", "SELL"],
            "quantity": [3, 3],
            "price": [100.0, 100.0],
        }
    )
    assert detect_wash_trades(trades).empty


def test_spoofing_ignores_slow_cancels():
    orders = pd.DataFrame(
        {
            "order_id": [f"O{i}" for i in range(6)],
            "account": ["A"] * 6,
            "instrument": ["CL"] * 6,
            "trade_date": ["2026-01-05"] * 6,
            "side": ["SELL"] * 6,
            "quantity": [200] * 6,
            "status": ["CANCELLED"] * 6,
            "cancel_seconds": [60.0] * 6,
        }
    )
    assert detect_spoofing(orders).empty


def test_marking_the_close_detects_late_move():
    rows = []
    for i in range(20):
        rows.append(
            {
                "trade_id": f"T{i}",
                "account": "A",
                "instrument": "ES",
                "trade_date": "2026-01-05",
                "timestamp": f"2026-01-05 10:{i:02d}:00",
                "side": "BUY",
                "quantity": 10,
                "price": 100.0,
            }
        )
    for i in range(3):
        rows.append(
            {
                "trade_id": f"L{i}",
                "account": "B",
                "instrument": "ES",
                "trade_date": "2026-01-05",
                "timestamp": f"2026-01-05 15:5{i}:00",
                "side": "BUY",
                "quantity": 10,
                "price": 101.0,
            }
        )
    findings = detect_marking_the_close(pd.DataFrame(rows))
    assert len(findings) == 1
    assert findings.iloc[0]["pattern"] == "marking_the_close"


def test_position_concentration_flags_dominant_account():
    positions = pd.DataFrame(
        {
            "account": ["A", "B", "C"],
            "instrument": ["ES"] * 3,
            "trade_date": ["2026-01-05"] * 3,
            "net_quantity": [90, 5, 5],
            "market_value": [9000.0, 500.0, 500.0],
        }
    )
    findings = detect_position_concentration(positions)
    assert len(findings) == 1
    assert findings.iloc[0]["account"] == "A"
    assert findings.iloc[0]["share_pct"] == 90.0


def test_run_all_combines_and_sorts(frames):
    orders, trades, positions = frames
    findings = run_all_detectors(orders, trades, positions)
    assert not findings.empty
    assert set(findings["pattern"].unique()) >= {"wash_trade", "spoofing"}
    assert findings["severity"].is_monotonic_decreasing
    assert findings["severity"].between(0, 100).all()
