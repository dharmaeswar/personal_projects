"""Tests for the public-finance sector screen and sales ideas."""

import pytest

from muni_engine import sector_relative_value, sector_summary, sales_ideas


def _screened():
    # residual_bp values are pre-computed screen outputs; sectors are mixed
    # so sector means differ from the market mean.
    return [
        {"id": "GO-1", "sector": "GO", "rating": "AAA", "maturity_years": 10,
         "coupon": 0.04, "callable": False, "spread_bp": 40,
         "predicted_spread_bp": 30.0, "residual_bp": 10.0, "yield_pct": 3.2,
         "flag": "FAIR"},
        {"id": "GO-2", "sector": "GO", "rating": "AA", "maturity_years": 20,
         "coupon": 0.05, "callable": True, "spread_bp": 90,
         "predicted_spread_bp": 55.0, "residual_bp": 35.0, "yield_pct": 4.1,
         "flag": "CHEAP"},
        {"id": "WS-1", "sector": "WATER_SEWER", "rating": "AA",
         "maturity_years": 15, "coupon": 0.04, "callable": True,
         "spread_bp": 70, "predicted_spread_bp": 50.0, "residual_bp": 20.0,
         "yield_pct": 3.8, "flag": "FAIR"},
        {"id": "WS-2", "sector": "WATER_SEWER", "rating": "A",
         "maturity_years": 25, "coupon": 0.05, "callable": True,
         "spread_bp": 160, "predicted_spread_bp": 80.0, "residual_bp": 80.0,
         "yield_pct": 4.6, "flag": "CHEAP"},
        {"id": "HOSP-1", "sector": "HOSPITAL", "rating": "BBB",
         "maturity_years": 12, "coupon": 0.045, "callable": True,
         "spread_bp": 120, "predicted_spread_bp": 90.0, "residual_bp": 30.0,
         "yield_pct": 4.4, "flag": "CHEAP"},
    ]


def test_sector_summary_counts_and_means():
    s = sector_summary(_screened())
    assert s["GO"]["count"] == 2
    assert s["GO"]["mean_spread_bp"] == 65.0
    assert s["GO"]["mean_residual_bp"] == 22.5
    assert s["WATER_SEWER"]["count"] == 2
    assert s["HOSPITAL"]["count"] == 1
    assert s["HOSPITAL"]["sector_name"] == "Hospital Revenue"


def test_sector_summary_unknown_sector_raises():
    rows = _screened()
    rows[0] = {**rows[0], "sector": "AIRPORT"}
    with pytest.raises(ValueError):
        sector_summary(rows)


def test_sector_residual_removes_sector_mean():
    out = sector_relative_value(_screened())
    by_id = {r["id"]: r for r in out}
    # GO mean residual is 22.5, so GO-2's sector residual is 35 - 22.5 = 12.5
    assert by_id["GO-2"]["sector_residual_bp"] == 12.5
    # WATER_SEWER mean residual is 50, so WS-2's sector residual is 30.0
    assert by_id["WS-2"]["sector_residual_bp"] == 30.0
    # HOSPITAL has one bond, so its sector residual is exactly 0
    assert by_id["HOSP-1"]["sector_residual_bp"] == 0.0


def test_sector_flag_uses_sector_residual_not_market_residual():
    # GO-2 is CHEAP market-wide (+35bp) but only +12.5bp vs its sector.
    out = sector_relative_value(_screened())
    by_id = {r["id"]: r for r in out}
    assert by_id["GO-2"]["flag"] == "CHEAP"
    assert by_id["GO-2"]["sector_flag"] == "FAIR"


def test_sector_flag_cheap_when_far_above_sector_peers():
    rows = _screened()
    rows.append({"id": "GO-3", "sector": "GO", "rating": "A",
                 "maturity_years": 30, "coupon": 0.05, "callable": True,
                 "spread_bp": 150, "predicted_spread_bp": 60.0,
                 "residual_bp": 90.0, "yield_pct": 5.0, "flag": "CHEAP"})
    out = sector_relative_value(rows)
    by_id = {r["id"]: r for r in out}
    # GO mean residual becomes (10 + 35 + 90) / 3 = 45; GO-3 is +45 vs peers
    assert by_id["GO-3"]["sector_flag"] == "CHEAP"
    assert by_id["GO-3"]["sector_residual_bp"] == 45.0


def test_sales_ideas_rank_by_sector_residual():
    ideas = sales_ideas(_screened(), top_n=3)
    # Only WS-2 (+30.0) clears the sector threshold here; GO-2 is CHEAP
    # market-wide but only +12.5bp vs its GO peers, so it is not an idea.
    assert [i["id"] for i in ideas] == ["WS-2"]
    assert ideas[0]["sector_residual_bp"] == 30.0


def test_sales_ideas_top_n_limits_and_orders():
    rows = _screened()
    rows.append({"id": "GO-3", "sector": "GO", "rating": "A",
                 "maturity_years": 30, "coupon": 0.05, "callable": True,
                 "spread_bp": 150, "predicted_spread_bp": 60.0,
                 "residual_bp": 90.0, "yield_pct": 5.0, "flag": "CHEAP"})
    ideas = sales_ideas(rows, top_n=1)
    assert len(ideas) == 1
    assert ideas[0]["id"] == "GO-3"
    assert ideas[0]["sector_residual_bp"] == 45.0


def test_sales_ideas_taxable_equivalent_yield():
    ideas = sales_ideas(_screened(), top_n=3, marginal_tax_rate=0.37)
    assert ideas
    # 4.6% tax-exempt at a 37% bracket -> 4.6 / 0.63 = 7.30%
    assert ideas[0]["taxable_equivalent_yield_pct"] == pytest.approx(7.30, abs=0.01)
    assert "7.30%" in ideas[0]["rationale"]
    assert "WS-2" in ideas[0]["rationale"]


def test_sales_ideas_invalid_tax_rate_raises():
    with pytest.raises(ValueError):
        sales_ideas(_screened(), marginal_tax_rate=1.0)


def test_sales_ideas_empty_when_nothing_cheap_vs_sector():
    rows = [{**r, "residual_bp": 0.0} for r in _screened()]
    assert sales_ideas(rows) == []
