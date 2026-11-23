"""Demo: price a small book three ways, bootstrap a curve, measure risk.

- Prices European calls/puts with Black-Scholes, the Crank-Nicolson PDE
  solver, and Monte Carlo, and prints how closely the three agree.
- Prices an arithmetic Asian call by Monte Carlo.
- Bootstraps a discount curve from par swap rates and re-verifies it.
- Computes 95% historical VaR / expected shortfall and parametric VaR
  on a synthetic return series, and aggregates the book's Greeks.

All data is synthetic. Pure standard library (plus pytest for tests).

Usage:
    PYTHONPATH=. python3 run_demo.py
"""

import json
import random

from pricing_lib import (
    DiscountCurve,
    aggregate_greeks,
    asian_mc,
    bs_greeks,
    bs_price,
    crank_nicolson_price,
    european_mc,
    historical_es,
    historical_var,
    parametric_var,
)

BOOK = [
    {"label": "Call 100/1y", "S": 100.0, "K": 100.0, "T": 1.0,
     "r": 0.05, "sigma": 0.20, "option": "call", "qty": 10},
    {"label": "Put 95/6m", "S": 100.0, "K": 95.0, "T": 0.5,
     "r": 0.05, "sigma": 0.25, "option": "put", "qty": -5},
    {"label": "Call 110/2y", "S": 100.0, "K": 110.0, "T": 2.0,
     "r": 0.04, "sigma": 0.22, "option": "call", "qty": 4},
]


def main():
    print("Book pricing — Black-Scholes vs PDE vs Monte Carlo")
    positions = []
    for leg in BOOK:
        bs = bs_price(leg["S"], leg["K"], leg["T"], leg["r"], leg["sigma"],
                      leg["option"])
        pde = crank_nicolson_price(leg["S"], leg["K"], leg["T"], leg["r"],
                                   leg["sigma"], leg["option"])
        mc = european_mc(leg["S"], leg["K"], leg["T"], leg["r"], leg["sigma"],
                         leg["option"], n_paths=40000, seed=7)
        greeks = bs_greeks(leg["S"], leg["K"], leg["T"], leg["r"],
                           leg["sigma"], leg["option"])
        positions.append((leg["qty"], greeks))
        print(f"  {leg['label']:>12}: BS={bs:7.4f} PDE={pde:7.4f} "
              f"MC={mc['price']:7.4f} +/- {1.96 * mc['stderr']:.4f} "
              f"(delta {greeks['delta']:+.3f}, vega {greeks['vega']:6.2f})")
    total = aggregate_greeks(positions)
    print("Book Greeks: " + json.dumps({k: round(v, 3) for k, v in total.items()}))

    asian = asian_mc(100.0, 100.0, 1.0, 0.05, 0.20, "call", n_paths=20000, seed=7)
    print(f"Asian call (monthly avg, 1y): MC={asian['price']:.4f} "
          f"+/- {1.96 * asian['stderr']:.4f} "
          f"(European BS is {bs_price(100.0, 100.0, 1.0, 0.05, 0.20, 'call'):.4f})")

    curve = DiscountCurve([(1, 0.020), (2, 0.025), (3, 0.028),
                           (5, 0.032), (10, 0.035)])
    print("Discount curve (par swaps 1y/2y/3y/5y/10y):")
    for tenor, rate in [(1, 0.020), (2, 0.025), (3, 0.028), (5, 0.032), (10, 0.035)]:
        print(f"  {tenor:>2}y: DF={curve.discount_factor(float(tenor)):.4f} "
              f"zero={curve.zero_rate(float(tenor)):.2%} "
              f"re-priced par={curve.par_swap_rate(tenor):.4%} (input {rate:.2%})")

    rng = random.Random(7)
    returns = [rng.gauss(0.0004, 0.012) for _ in range(500)]
    print(f"Risk (500 synthetic daily returns): 95% hist VaR="
          f"{historical_var(returns):.2%}, ES={historical_es(returns):.2%}, "
          f"parametric VaR={parametric_var(returns):.2%}")


if __name__ == "__main__":
    main()
