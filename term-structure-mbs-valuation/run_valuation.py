"""Demo valuation run: fit a curve to illustrative Treasury zero yields,
price a sample agency pass-through pool statically and by Monte Carlo,
solve its OAS to a sample market price, and report rate risk.

Run:  python run_valuation.py
"""

from __future__ import annotations

import numpy as np

from term_structure_mbs import (
    HullWhiteModel,
    Pool,
    effective_duration_convexity,
    fit_nelson_siegel,
    mc_price,
    scenario_prices,
    solve_oas,
    static_price,
)

# Illustrative Treasury zero yields (decimals) as of a sample date.
MATURITIES = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30], dtype=float)
YIELDS = np.array([0.052, 0.051, 0.049, 0.046, 0.044, 0.0425, 0.0425, 0.0435, 0.046, 0.0455])


def main() -> None:
    curve, rmse = fit_nelson_siegel(MATURITIES, YIELDS, svensson=True)
    print(f"Fitted curve: {curve!r}")
    print(f"Fit RMSE: {rmse * 1e4:.2f} bp")
    print(f"Zero rates: 2y={curve.zero_rate(2):.4%}  10y={curve.zero_rate(10):.4%}  "
          f"30y={curve.zero_rate(30):.4%}")
    print(f"Forward 5y5y: {curve.forward(5, 10):.4%}")

    pool = Pool(balance=250_000_000, wac=0.060, net_coupon=0.055, wam_months=360, psa=100.0)
    p_static = static_price(pool, curve)
    print(f"\nPool: $250mm, WAC 6.00%, net 5.50%, WAM 360, 100 PSA")
    print(f"Static price:            {p_static:.4f}")

    hw = HullWhiteModel(curve, a=0.10, sigma=0.008)
    p_mc = mc_price(pool, hw, n_paths=200, seed=11)
    print(f"Monte Carlo price (HW):  {p_mc:.4f}")

    market_price = 101.25
    oas = solve_oas(pool, curve, market_price)
    print(f"OAS to {market_price:.2f}:          {oas * 1e4:.1f} bp")

    dur, conv = effective_duration_convexity(pool, curve)
    print(f"Effective duration:      {dur:.3f}")
    print(f"Effective convexity:     {conv:.3f}")

    scenarios = scenario_prices(pool, curve, {"down_100bp": -0.01, "down_50bp": -0.005,
                                              "up_50bp": 0.005, "up_100bp": 0.01})
    print("\nScenario prices:")
    for name, price in scenarios.items():
        print(f"  {name:>10}: {price:.4f}")


if __name__ == "__main__":
    main()
