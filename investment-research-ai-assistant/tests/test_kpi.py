"""Tests for the single-stock KPI inflection module (kpi.py)."""

import copy

import pytest

from research_assistant.kpi import (
    alt_momentum,
    backtest_kpi_signal,
    dashboard_summary,
    detect_inflections,
    forecast_kpi,
    kpi_report,
    kpi_signal,
    load_kpi_panel,
)


def test_panel_has_four_companies_twelve_quarters():
    panel = load_kpi_panel()
    assert len(panel) == 4
    assert {c.company for c in panel} == {
        "Acme Industrial Holdings",
        "Beacon Health Systems",
        "Northwind Energy Partners",
        "Helix Software Group",
    }
    for company in panel:
        assert len(company.quarters) == 12
        assert len(company.revenue_growth) == 12
        assert len(company.operating_margin) == 12
        assert len(company.alt_index) == 12
        assert len(company.stock_return) == 12


def test_panel_is_deterministic_for_a_seed():
    first = load_kpi_panel(seed=42)
    second = load_kpi_panel(seed=42)
    assert first == second
    assert load_kpi_panel(seed=7) != first


def test_detect_inflections_finds_planted_helix_break():
    panel = load_kpi_panel()
    helix = next(c for c in panel if c.company == "Helix Software Group")
    breaks = detect_inflections(helix.revenue_growth)
    assert breaks, "planted Helix revenue step-up was not detected"
    assert any(b["direction"] == "up" and b["index"] == 6 for b in breaks)


def test_detect_inflections_finds_planted_northwind_break():
    panel = load_kpi_panel()
    northwind = next(c for c in panel if c.company == "Northwind Energy Partners")
    breaks = detect_inflections(northwind.operating_margin)
    assert breaks, "planted Northwind margin step-down was not detected"
    assert any(b["direction"] == "down" and b["index"] == 8 for b in breaks)


def test_detect_inflections_quiet_on_flat_series():
    assert detect_inflections([10.0] * 12) == []
    assert detect_inflections([5.0, 5.1, 4.9, 5.0, 5.1, 4.9, 5.0, 5.1]) == []


def test_detect_inflections_needs_a_trailing_window():
    assert detect_inflections([1.0, 2.0, 3.0]) == []


def test_forecast_recovers_known_slope():
    series = [2.0 * i + 1.0 for i in range(10)]
    result = forecast_kpi(series)
    assert result["slope"] == pytest.approx(2.0, abs=0.01)
    assert result["forecast"] == pytest.approx(21.0, abs=0.01)
    assert result["r_squared"] == pytest.approx(1.0, abs=0.001)


def test_forecast_needs_at_least_three_points():
    with pytest.raises(ValueError):
        forecast_kpi([1.0, 2.0])


def test_alt_momentum_matches_manual_change():
    assert alt_momentum([100.0, 102.0, 104.0, 106.0, 110.0], window=4) == pytest.approx(10.0)


def test_kpi_signal_is_bounded_and_scored():
    panel = load_kpi_panel()
    for company in panel:
        signal = kpi_signal(company)
        assert -3 <= signal["score"] <= 3
        assert set(signal) >= {"company", "score", "inflection", "trend", "alt_sign"}


def test_kpi_signal_has_no_look_ahead():
    panel = load_kpi_panel()
    company = copy.deepcopy(panel[0])
    before = kpi_signal(company, upto=6)
    # Corrupt all data after quarter 6: the signal at quarter 6 must not move.
    company.revenue_growth[7:] = [999.0] * 5
    company.alt_index[7:] = [9999.0] * 5
    assert kpi_signal(company, upto=6) == before


def test_backtest_runs_without_look_ahead_and_reports_metrics():
    panel = load_kpi_panel()
    result = backtest_kpi_signal(panel)
    assert result["n_trades"] == 7  # quarters 5..11 formed, held one quarter later
    assert 0.0 <= result["hit_rate"] <= 1.0
    assert result["total_return_pct"] == pytest.approx(
        sum(t["net_return_pct"] for t in result["trades"]), abs=0.01)
    for trade in result["trades"]:
        assert trade["long"] != trade["short"]
        assert trade["holding_quarter"] > trade["formation_quarter"]


def test_dashboard_rows_are_complete():
    panel = load_kpi_panel()
    rows = dashboard_summary(panel)
    assert len(rows) == 4
    for row in rows:
        assert row["position"] in {"LONG", "SHORT", "NEUTRAL"}
        assert -3 <= row["signal_score"] <= 3
        assert row["latest_revenue_growth_pct"] is not None
        assert row["next_quarter_revenue_growth_forecast_pct"] is not None


def test_kpi_report_end_to_end():
    report = kpi_report()
    assert len(report["dashboard"]) == 4
    assert report["backtest"]["n_trades"] == 7
    assert len(report["quarters"]) == 12
