"""Customer forecasting: from top-line drivers through to gross profit.

Forecast method (documented, reproducible, no hidden steps):
  active_cards grows by a monthly growth rate;
  TPV = active_cards * avg_txns_per_card * avg_ticket;
  transactions = active_cards * avg_txns_per_card;
  revenue and costs come from the same PricingTerms used for actuals,
  so forecast and actuals are directly comparable for variance analysis.
Scenarios scale the growth rate and avg ticket: base 1.00x, upside 1.10x,
downside 0.90x.
"""
from dataclasses import dataclass
from decimal import Decimal

from .economics import MonthActuals, MonthEconomics, PricingTerms, month_economics, money


@dataclass(frozen=True)
class ForecastDrivers:
    active_cards: int
    monthly_card_growth_pct: Decimal   # e.g. 2.0 = +2% per month
    avg_txns_per_card: Decimal
    avg_ticket: Decimal                # dollars per transaction


@dataclass(frozen=True)
class ForecastMonth:
    customer: str
    month: str
    active_cards: int
    tpv: Decimal
    transactions: int
    gross_profit: Decimal


def forecast_months(customer: str, start_month: str, months: int,
                    drivers: ForecastDrivers, terms: PricingTerms,
                    scenario_factor: Decimal = Decimal("1.00")) -> list:
    """Forecast `months` months starting at `start_month` (YYYY-MM)."""
    if months < 1:
        raise ValueError("months must be at least 1")
    if drivers.active_cards <= 0:
        raise ValueError("active_cards must be positive")
    year, mon = int(start_month[:4]), int(start_month[5:7])
    cards = Decimal(drivers.active_cards)
    growth = Decimal("1") + drivers.monthly_card_growth_pct / Decimal("100")
    out = []
    for i in range(months):
        txns = int((cards * drivers.avg_txns_per_card).to_integral_value())
        tpv = money(cards * drivers.avg_txns_per_card * drivers.avg_ticket
                    * scenario_factor)
        actuals = MonthActuals(customer=customer,
                               month=f"{year:04d}-{mon:02d}",
                               tpv=tpv, transactions=txns)
        econ = month_economics(actuals, terms)
        out.append(ForecastMonth(customer=customer, month=econ.month,
                                 active_cards=int(cards.to_integral_value()),
                                 tpv=econ.tpv, transactions=txns,
                                 gross_profit=econ.gross_profit))
        cards = cards * growth
        mon += 1
        if mon > 12:
            mon, year = 1, year + 1
    return out


def scenario_forecast(customer: str, start_month: str, months: int,
                      drivers: ForecastDrivers, terms: PricingTerms) -> dict:
    """Base / upside / downside forecasts; returns totals per scenario."""
    factors = {"base": Decimal("1.00"), "upside": Decimal("1.10"),
               "downside": Decimal("0.90")}
    result = {}
    for name, factor in factors.items():
        rows = forecast_months(customer, start_month, months, drivers, terms, factor)
        result[name] = {
            "months": rows,
            "total_tpv": sum((r.tpv for r in rows), Decimal("0.00")),
            "total_gross_profit": sum((r.gross_profit for r in rows),
                                      Decimal("0.00")),
        }
    return result
