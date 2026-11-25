"""Tests for expected-vs-realised performance attribution."""

import pytest

from muni_engine import attribute_performance, performance_bridge


def _drivers():
    return [
        {"name": "Rates", "contribution_pct": -0.20},
        {"name": "Spread", "contribution_pct": -0.10},
        {"name": "Curve", "contribution_pct": 0.05},
    ]


def test_gap_and_explained():
    # expected 1.20, realised 0.85 -> gap -0.35; drivers sum to -0.25
    result = attribute_performance(1.20, 0.85, _drivers())
    assert result["gap_pct"] == pytest.approx(-0.35)
    assert result["explained_pct"] == pytest.approx(-0.25)
    assert result["unexplained_pct"] == pytest.approx(-0.10)


def test_market_driven_within_tolerance():
    # unexplained -0.10 is exactly at the 0.10 tolerance -> market-driven
    result = attribute_performance(1.20, 0.85, _drivers())
    assert result["verdict"] == "MARKET-DRIVEN"


def test_data_model_issue_when_unexplained_is_large():
    # realised 0.60 -> gap -0.60, unexplained -0.35: too big for the drivers
    result = attribute_performance(1.20, 0.60, _drivers())
    assert result["unexplained_pct"] == pytest.approx(-0.35)
    assert result["verdict"] == "DATA/MODEL ISSUE - INVESTIGATE"


def test_outperformance_market_driven():
    drivers = [{"name": "Rates", "contribution_pct": 0.30},
               {"name": "Spread", "contribution_pct": 0.12}]
    result = attribute_performance(1.00, 1.42, drivers)
    assert result["unexplained_pct"] == pytest.approx(0.0)
    assert result["verdict"] == "MARKET-DRIVEN"


def test_no_drivers_means_all_unexplained():
    result = attribute_performance(1.00, 0.80, [])
    assert result["explained_pct"] == 0.0
    assert result["unexplained_pct"] == pytest.approx(-0.20)
    assert result["verdict"] == "DATA/MODEL ISSUE - INVESTIGATE"


def test_bridge_walks_expected_to_realised():
    bridge = performance_bridge(1.20, 0.85, _drivers())
    rows = dict(bridge["bridge"])
    assert rows["Expected return"] == 1.20
    assert rows["Rates"] == pytest.approx(1.00)
    assert rows["Spread"] == pytest.approx(0.90)
    assert rows["Curve"] == pytest.approx(0.95)
    assert rows["Unexplained residual"] == pytest.approx(0.85)
    assert rows["Realised return"] == 0.85
    assert bridge["verdict"] == "MARKET-DRIVEN"
    assert bridge["unexplained_pct"] == pytest.approx(-0.10)


def test_bridge_flags_data_model_issue():
    bridge = performance_bridge(1.20, 0.60, _drivers())
    assert bridge["verdict"] == "DATA/MODEL ISSUE - INVESTIGATE"
    assert bridge["unexplained_pct"] == pytest.approx(-0.35)
