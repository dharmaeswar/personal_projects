"""Run the commodity derivatives pricing and risk demo.

Builds futures curves for WTI, natural gas and gold, prices options
on the front futures with Black-76, runs the validation checks, and
measures VaR on a small book. Writes ``commodities_report.txt`` next
to this script. All data is synthetic and seeded; no real market data
is used.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from commodities.curves import curve_summary, implied_convenience_yield
from commodities.data import COMMODITIES, generate_futures_curve, generate_spot_paths
from commodities.pricing import black76_call, black76_greeks, black76_put, implied_vol
from commodities.risk import book_value, historical_var, monte_carlo_var, scenario_shocks
from commodities.validation import (
    check_greeks_finite_difference,
    check_mc_convergence,
    check_put_call_parity,
)

HERE = Path(__file__).resolve().parent
R = 0.045

# A small book: long 100 WTI futures, long 50 natgas futures, short 2
# gold futures (gold's price dwarfs the others, so 2 contracts keep the
# book roughly balanced), plus 20 WTI calls and 10 natgas puts on the
# front future. The book is net long, so a down move loses money.
BOOK = [
    {"type": "future", "commodity": "WTI", "qty": 100.0},
    {"type": "future", "commodity": "NATGAS", "qty": 50.0},
    {"type": "future", "commodity": "GOLD", "qty": -2.0},
    {"type": "call", "commodity": "WTI", "qty": 20.0, "strike": 80.0, "T": 0.5, "sigma": 0.32},
    {"type": "put", "commodity": "NATGAS", "qty": 10.0, "strike": 3.0, "T": 0.25, "sigma": 0.65},
]


def main() -> None:
    lines = ["COMMODITY DERIVATIVES PRICING & RISK REPORT", ""]
    spots = generate_spot_paths()
    last_spot = {c: float(spots[c].iloc[-1]) for c in COMMODITIES}
    lines.append(f"last simulated spot: " + ", ".join(f"{c} {v:.2f}" for c, v in last_spot.items()))
    lines.append("")

    # Futures curves from cost of carry.
    lines.append("futures curves (cost of carry):")
    for name, spec in COMMODITIES.items():
        carry = {"WTI": (0.08, 0.05), "NATGAS": (0.10, 0.02), "GOLD": (0.01, 0.00)}[name]
        curve = generate_futures_curve(
            last_spot[name], R, storage_cost=carry[0], convenience_yield=carry[1]
        )
        summary = curve_summary(curve)
        y = implied_convenience_yield(
            last_spot[name], float(curve["futures_price"].iloc[5]), 0.5, R, carry[0]
        )
        lines.append(
            f"  {name}: front {summary['front_price']}, 12M {summary['deferred_price']}, "
            f"{summary['shape']}, avg monthly spread {summary['avg_monthly_spread']}, "
            f"implied convenience yield (6M) {y:.3f}"
        )
    lines.append("")

    # Option pricing on the front WTI future.
    F = float(generate_futures_curve(last_spot["WTI"], R, 0.08, 0.05)["futures_price"].iloc[0])
    K, T, sigma = 80.0, 0.5, 0.32
    call = black76_call(F, K, T, R, sigma)
    put = black76_put(F, K, T, R, sigma)
    greeks = black76_greeks(F, K, T, R, sigma, "call")
    iv = implied_vol(call, F, K, T, R, "call")
    lines.append(f"WTI front future {F:.2f}; 6M call K=80: {call:.2f}, put: {put:.2f}")
    lines.append(
        f"  call Greeks: delta {greeks['delta']:.4f}, gamma {greeks['gamma']:.5f}, "
        f"vega {greeks['vega']:.2f} (per 100% vol), theta {greeks['theta']:.2f}/yr"
    )
    lines.append(f"  implied vol recovered from the call price: {iv:.4f} (input {sigma})")
    lines.append("")

    # Validation checks.
    lines.append("validation checks:")
    for check in (
        check_put_call_parity(F, K, T, R, sigma),
        check_mc_convergence(F, K, T, R, sigma),
        check_greeks_finite_difference(F, K, T, R, sigma),
    ):
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  [{status}] {check['check']}: {check}")
    lines.append("")

    # Book risk: historical and Monte Carlo VaR, scenarios.
    returns = np.log(spots / spots.shift(1)).dropna()
    base = book_value(BOOK, last_spot, R)
    lines.append(f"book value: {base:.2f}")
    hvar = historical_var(returns, BOOK, last_spot, R, 0.95)
    hvar99 = historical_var(returns, BOOK, last_spot, R, 0.99)
    mcvar = monte_carlo_var(
        BOOK, last_spot, {c: COMMODITIES[c]["vol"] for c in COMMODITIES}, R, 0.95
    )
    lines.append(
        f"historical VaR 95%: {hvar['var']}, ES 95%: {hvar['expected_shortfall']}, "
        f"worst day P&L: {hvar['worst_day_pnl']}"
    )
    lines.append(f"historical VaR 99%: {hvar99['var']}, ES 99%: {hvar99['expected_shortfall']}")
    lines.append(
        f"Monte Carlo VaR 95%: {mcvar['var']}, ES 95%: {mcvar['expected_shortfall']} "
        f"(independent shocks; labelled approximation)"
    )
    lines.append("scenario P&L:")
    for _, row in scenario_shocks(BOOK, last_spot, R).iterrows():
        lines.append(f"  {row['scenario']} (vol bump {row['vol_bump']:+.2f}): {row['pnl']}")
    lines.append("")

    (HERE / "commodities_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
