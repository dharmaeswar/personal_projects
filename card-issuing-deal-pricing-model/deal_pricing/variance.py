"""Variance analysis: explain why gross profit moved vs forecast.

Decomposes the profit gap into named drivers so the commentary written for
sales and leadership is traceable to numbers, not adjectives:
  - volume variance: TPV moved, at forecast margin;
  - rate variance: the realised take rate (profit per $ TPV) moved;
  - fixed-cost variance: fixed cost moved vs forecast.
The three drivers sum exactly to the total profit variance (cents).
"""
from dataclasses import dataclass
from decimal import Decimal

from .economics import money


@dataclass(frozen=True)
class Variance:
    customer: str
    month: str
    forecast_profit: Decimal
    actual_profit: Decimal
    total_variance: Decimal
    volume_variance: Decimal
    rate_variance: Decimal
    fixed_cost_variance: Decimal

    def commentary(self) -> str:
        """One plain-language paragraph for the monthly deck."""
        direction = "above" if self.total_variance >= 0 else "below"
        parts = [
            f"{self.customer} {self.month}: gross profit ${self.actual_profit:,.2f}, "
            f"${abs(self.total_variance):,.2f} {direction} forecast "
            f"(${self.forecast_profit:,.2f})."
        ]
        drivers = []
        if self.volume_variance != 0:
            drivers.append(f"volume {'added' if self.volume_variance > 0 else 'cost'} "
                            f"${abs(self.volume_variance):,.2f}")
        if self.rate_variance != 0:
            drivers.append(f"take rate {'added' if self.rate_variance > 0 else 'cost'} "
                            f"${abs(self.rate_variance):,.2f}")
        if self.fixed_cost_variance != 0:
            drivers.append(f"fixed cost {'saved' if self.fixed_cost_variance > 0 else 'cost'} "
                            f"${abs(self.fixed_cost_variance):,.2f}")
        if drivers:
            parts.append("Drivers: " + "; ".join(drivers) + ".")
        else:
            parts.append("No driver moved; profit matched forecast.")
        return " ".join(parts)


def analyse_variance(customer: str, month: str,
                     forecast_tpv: Decimal, forecast_profit: Decimal,
                     forecast_fixed: Decimal,
                     actual_tpv: Decimal, actual_profit: Decimal,
                     actual_fixed: Decimal) -> Variance:
    """Decompose actual-vs-forecast gross profit into three drivers."""
    if forecast_tpv < 0 or actual_tpv < 0:
        raise ValueError("TPV must not be negative")
    forecast_rate = (
        (forecast_profit + forecast_fixed) / forecast_tpv
        if forecast_tpv > 0 else Decimal("0")
    )
    actual_rate = (
        (actual_profit + actual_fixed) / actual_tpv
        if actual_tpv > 0 else Decimal("0")
    )
    volume_var = money((actual_tpv - forecast_tpv) * forecast_rate)
    rate_var = money(actual_tpv * (actual_rate - forecast_rate))
    fixed_var = money(forecast_fixed - actual_fixed)
    total = money(actual_profit - forecast_profit)
    # The three drivers must sum to the total; any cent-level rounding gap
    # goes to the rate variance, the least structural driver.
    gap = total - (volume_var + rate_var + fixed_var)
    rate_var = money(rate_var + gap)
    return Variance(
        customer=customer, month=month,
        forecast_profit=money(forecast_profit), actual_profit=money(actual_profit),
        total_variance=total, volume_variance=volume_var,
        rate_variance=rate_var, fixed_cost_variance=fixed_var,
    )
