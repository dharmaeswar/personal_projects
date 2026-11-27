"""End-to-end demo: seed 3 synthetic customers, forecast, price a deal,
explain a variance, reconcile Python vs SQL, and write the monthly deck
support files into reports/.

All data is synthetic and seeded in code. No real company or customer data
appears anywhere, and nothing here was used in production.
"""
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deal_pricing import (
    PricingTerms, MonthActuals, month_economics, portfolio_totals,
    ForecastDrivers, forecast_months, scenario_forecast,
    model_deal, analyse_variance,
    load_to_sqlite, reconcile,
)
from deal_pricing.report import write_monthly_csv, write_forecast_csv, write_summary

BASE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(BASE, "reports")
os.makedirs(REPORTS, exist_ok=True)

TERMS = {
    "Northwind Retail": PricingTerms(
        interchange_bps=Decimal("145"), network_bps=Decimal("12"),
        bank_bps=Decimal("25"), per_txn_fee=Decimal("0.04"),
        fixed_monthly=Decimal("8500")),
    "Helios Travel": PricingTerms(
        interchange_bps=Decimal("160"), network_bps=Decimal("13"),
        bank_bps=Decimal("28"), per_txn_fee=Decimal("0.05"),
        fixed_monthly=Decimal("12000")),
    "Bluepeak Groceries": PricingTerms(
        interchange_bps=Decimal("130"), network_bps=Decimal("11"),
        bank_bps=Decimal("22"), per_txn_fee=Decimal("0.03"),
        fixed_monthly=Decimal("6000")),
}

ACTUALS = [
    ("Northwind Retail", "2026-10", Decimal("4200000"), 84000),
    ("Northwind Retail", "2026-11", Decimal("4650000"), 92000),
    ("Helios Travel", "2026-10", Decimal("2800000"), 41000),
    ("Helios Travel", "2026-11", Decimal("3100000"), 44500),
    ("Bluepeak Groceries", "2026-10", Decimal("6100000"), 152000),
    ("Bluepeak Groceries", "2026-11", Decimal("5980000"), 148000),
]

FORECAST_DRIVERS = {
    "Northwind Retail": ForecastDrivers(
        active_cards=52000, monthly_card_growth_pct=Decimal("2.0"),
        avg_txns_per_card=Decimal("1.8"), avg_ticket=Decimal("50")),
    "Helios Travel": ForecastDrivers(
        active_cards=31000, monthly_card_growth_pct=Decimal("3.0"),
        avg_txns_per_card=Decimal("1.4"), avg_ticket=Decimal("72")),
    "Bluepeak Groceries": ForecastDrivers(
        active_cards=98000, monthly_card_growth_pct=Decimal("1.0"),
        avg_txns_per_card=Decimal("1.55"), avg_ticket=Decimal("40")),
}

# Forecast for the October actuals (the month we explain below).
FORECAST_OCT = {
    "Northwind Retail": (Decimal("4000000"), Decimal("38500")),
    "Helios Travel": (Decimal("2900000"), Decimal("31000")),
    "Bluepeak Groceries": (Decimal("6200000"), Decimal("42000")),
}


def main() -> int:
    months = [month_economics(
        MonthActuals(customer=c, month=m, tpv=t, transactions=n), TERMS[c])
        for c, m, t, n in ACTUALS]
    totals = portfolio_totals(months)

    conn = load_to_sqlite(months)
    mismatches = reconcile(totals, conn)
    if mismatches:
        print("RECONCILIATION FAILED:")
        for m in mismatches:
            print(" -", m)
        return 1
    print("Reconciled: Python totals match SQL GROUP BY totals.")

    forecasts = {}
    for customer, drivers in FORECAST_DRIVERS.items():
        forecasts[customer] = forecast_months(
            customer, "2026-12", 6, drivers, TERMS[customer])
    scenarios = scenario_forecast(
        "Northwind Retail", "2026-12", 6,
        FORECAST_DRIVERS["Northwind Retail"], TERMS["Northwind Retail"])
    print("Northwind 6-month gross profit — base "
          f"${scenarios['base']['total_gross_profit']:,.2f}, upside "
          f"${scenarios['upside']['total_gross_profit']:,.2f}, downside "
          f"${scenarios['downside']['total_gross_profit']:,.2f}.")

    # Deal in negotiation: Helios renews at 150 bps interchange (from 160)
    # and 24 bps bank share (from 28) in exchange for committed volume.
    deal_terms = PricingTerms(
        interchange_bps=Decimal("150"), network_bps=Decimal("13"),
        bank_bps=Decimal("24"), per_txn_fee=Decimal("0.05"),
        fixed_monthly=Decimal("12000"))
    deal = model_deal("Helios Travel", "2026-12", Decimal("3400000"), 47000,
                      TERMS["Helios Travel"], deal_terms)
    print(f"Helios deal: incremental gross profit "
          f"${deal.incremental_gross_profit:,.2f}/mo "
          f"({deal.incremental_margin_bps} bps of TPV); break-even TPV "
          f"${deal.break_even_tpv:,.2f}." if deal.break_even_tpv
          else "Helios deal: no break-even TPV in range.")
    print("Deal sensitivity (volume change -> incremental profit): "
          + ", ".join(f"{p:+d}%: ${v:,.2f}" for p, v in deal.sensitivity.items()))

    variances = []
    for m in months:
        if m.month != "2026-10":
            continue
        f_tpv, f_profit = FORECAST_OCT[m.customer]
        variances.append(analyse_variance(
            m.customer, m.month, f_tpv, f_profit, TERMS[m.customer].fixed_monthly,
            m.tpv, m.gross_profit, TERMS[m.customer].fixed_monthly))
    for v in variances:
        print(v.commentary())

    write_monthly_csv(months, os.path.join(REPORTS, "monthly_economics.csv"))
    all_forecasts = [r for rows in forecasts.values() for r in rows]
    write_forecast_csv(all_forecasts, os.path.join(REPORTS, "forecast_6mo.csv"))
    write_summary(variances, totals, os.path.join(REPORTS, "summary.txt"))

    out = {
        "portfolio_totals": {k: str(v) for k, v in totals.items()},
        "deal_helios": {
            "current_gross_profit": str(deal.current_gross_profit),
            "deal_gross_profit": str(deal.deal_gross_profit),
            "incremental_gross_profit": str(deal.incremental_gross_profit),
            "break_even_tpv": str(deal.break_even_tpv),
            "sensitivity": {str(k): str(v) for k, v in deal.sensitivity.items()},
        },
        "scenarios_northwind_6mo": {
            k: str(v["total_gross_profit"]) for k, v in scenarios.items()
        },
        "reconciled": True,
    }
    with open(os.path.join(REPORTS, "run_summary.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"Reports written to {REPORTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
