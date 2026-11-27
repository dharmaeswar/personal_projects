from decimal import Decimal

import pytest

from deal_pricing import (
    PricingTerms, MonthActuals, month_economics, portfolio_totals,
    ForecastDrivers, forecast_months, scenario_forecast,
    model_deal, analyse_variance,
    load_to_sqlite, sql_totals, reconcile,
)

TERMS = PricingTerms(
    interchange_bps=Decimal("150"), network_bps=Decimal("12"),
    bank_bps=Decimal("25"), per_txn_fee=Decimal("0.04"),
    fixed_monthly=Decimal("10000"))


def test_month_economics_arithmetic():
    # TPV $1,000,000, 20,000 txns: interchange 15,000; network 1,200;
    # bank 2,500; processing 800; fixed 10,000 -> profit 500.
    econ = month_economics(
        MonthActuals("Acme", "2026-10", Decimal("1000000"), 20000), TERMS)
    assert econ.interchange == Decimal("15000.00")
    assert econ.network_fees == Decimal("1200.00")
    assert econ.bank_cost == Decimal("2500.00")
    assert econ.processing_cost == Decimal("800.00")
    assert econ.gross_profit == Decimal("500.00")
    assert econ.gross_margin_pct == Decimal("3.33")


def test_zero_volume_is_zero_profit_minus_fixed():
    econ = month_economics(
        MonthActuals("Acme", "2026-10", Decimal("0"), 0), TERMS)
    assert econ.gross_profit == Decimal("-10000.00")
    assert econ.gross_margin_pct == Decimal("0.00")


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        MonthActuals("Acme", "2026-10", Decimal("-1"), 0)
    with pytest.raises(ValueError):
        PricingTerms(Decimal("-1"), Decimal("12"), Decimal("25"),
                     Decimal("0.04"), Decimal("10000"))


def test_portfolio_totals_sum():
    months = [
        month_economics(MonthActuals("A", "2026-10", Decimal("1000000"), 20000), TERMS),
        month_economics(MonthActuals("B", "2026-10", Decimal("500000"), 10000), TERMS),
    ]
    totals = portfolio_totals(months)
    assert totals["tpv"] == Decimal("1500000.00")
    assert totals["transactions"] == 30000
    assert totals["gross_profit"] == Decimal("500.00") + Decimal("-4750.00")


def test_forecast_grows_cards_and_tpv():
    drivers = ForecastDrivers(
        active_cards=10000, monthly_card_growth_pct=Decimal("2.0"),
        avg_txns_per_card=Decimal("2"), avg_ticket=Decimal("50"))
    rows = forecast_months("Acme", "2026-12", 3, drivers, TERMS)
    assert len(rows) == 3
    assert [r.month for r in rows] == ["2026-12", "2027-01", "2027-02"]
    assert rows[0].tpv == Decimal("1000000.00")
    assert rows[1].tpv > rows[0].tpv  # card growth raises volume
    assert rows[0].active_cards == 10000
    assert rows[1].active_cards == 10200


def test_forecast_rejects_bad_inputs():
    drivers = ForecastDrivers(
        active_cards=0, monthly_card_growth_pct=Decimal("2.0"),
        avg_txns_per_card=Decimal("2"), avg_ticket=Decimal("50"))
    with pytest.raises(ValueError):
        forecast_months("Acme", "2026-12", 3, drivers, TERMS)


def test_scenarios_ordered_upside_above_downside():
    drivers = ForecastDrivers(
        active_cards=10000, monthly_card_growth_pct=Decimal("2.0"),
        avg_txns_per_card=Decimal("2"), avg_ticket=Decimal("50"))
    out = scenario_forecast("Acme", "2026-12", 3, drivers, TERMS)
    assert (out["upside"]["total_gross_profit"]
            > out["base"]["total_gross_profit"]
            > out["downside"]["total_gross_profit"])


def test_deal_model_incremental_profit():
    # Deal cuts interchange 150 -> 145 bps but bank share 25 -> 15 bps:
    # net take rises 5 bps, so at $1m TPV the deal adds $500/mo.
    deal_terms = PricingTerms(
        interchange_bps=Decimal("145"), network_bps=Decimal("12"),
        bank_bps=Decimal("15"), per_txn_fee=Decimal("0.04"),
        fixed_monthly=Decimal("10000"))
    result = model_deal("Acme", "2026-12", Decimal("1000000"), 20000,
                        TERMS, deal_terms)
    assert result.incremental_gross_profit == Decimal("500.00")
    assert result.incremental_margin_bps == Decimal("5.00")
    assert result.break_even_tpv is not None
    assert result.break_even_tpv <= Decimal("1000000.00")
    assert result.sensitivity[20] > result.sensitivity[-20]


def test_deal_model_worse_deal_has_high_break_even():
    # Deal cuts interchange 150 -> 100 bps, nothing else changes: the deal
    # loses $5,000/mo at committed volume and only breaks even at far
    # higher volume than committed.
    deal_terms = PricingTerms(
        interchange_bps=Decimal("100"), network_bps=Decimal("12"),
        bank_bps=Decimal("25"), per_txn_fee=Decimal("0.04"),
        fixed_monthly=Decimal("10000"))
    result = model_deal("Acme", "2026-12", Decimal("1000000"), 20000,
                        TERMS, deal_terms)
    assert result.incremental_gross_profit == Decimal("-5000.00")
    assert result.break_even_tpv is None or result.break_even_tpv > Decimal("1000000")


def test_variance_drivers_sum_to_total():
    v = analyse_variance(
        "Acme", "2026-10",
        forecast_tpv=Decimal("1000000"), forecast_profit=Decimal("500"),
        forecast_fixed=Decimal("10000"),
        actual_tpv=Decimal("1100000"), actual_profit=Decimal("1600"),
        actual_fixed=Decimal("10000"))
    assert v.total_variance == Decimal("1100.00")
    assert (v.volume_variance + v.rate_variance + v.fixed_cost_variance
            == v.total_variance)
    assert v.volume_variance == Decimal("1050.00")  # 10% more TPV at 1.05% rate


def test_variance_commentary_names_direction_and_drivers():
    v = analyse_variance(
        "Acme", "2026-10",
        forecast_tpv=Decimal("1000000"), forecast_profit=Decimal("500"),
        forecast_fixed=Decimal("10000"),
        actual_tpv=Decimal("900000"), actual_profit=Decimal("-200"),
        actual_fixed=Decimal("10000"))
    text = v.commentary()
    assert "below forecast" in text
    assert "volume" in text


def test_reconcile_passes_and_catches_tampering():
    months = [
        month_economics(MonthActuals("A", "2026-10", Decimal("1000000"), 20000), TERMS),
        month_economics(MonthActuals("B", "2026-10", Decimal("500000"), 10000), TERMS),
    ]
    totals = portfolio_totals(months)
    conn = load_to_sqlite(months)
    assert reconcile(totals, conn) == []
    assert sql_totals(conn)["gross_profit"] == totals["gross_profit"]
    tampered = dict(totals)
    tampered["gross_profit"] = totals["gross_profit"] + Decimal("5.00")
    assert reconcile(tampered, conn)  # $5 gap is caught
