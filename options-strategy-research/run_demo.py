"""End-to-end demo: data -> chain -> surface checks -> strategies -> backtest.

Run from the project root:  python3 run_demo.py
Outputs land in demo_out/: chain.csv, prices.json, pnl.csv, report.txt.
"""

import os

from options.data import (simulate_underlying, build_chain,
                          write_chain_csv, read_chain_csv,
                          write_prices_json)
from options.surface import run_all_checks
from options.strategies import (build_straddle, build_covered_call,
                                build_iron_condor, payoff_curve)
from options.backtest import run_study, study_summary
from options.visualize import ascii_payoff, write_pnl_csv

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_out")
RATE = 0.05
VOL = 0.25


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1. Data acquisition: seeded underlying path + option chain, stored to disk.
    prices = simulate_underlying(start=100.0, days=252, seed=42)
    write_prices_json(prices, os.path.join(OUT, "prices.json"))
    spot = prices[-1]
    chain = build_chain(spot)
    write_chain_csv(chain, os.path.join(OUT, "chain.csv"))
    chain = read_chain_csv(os.path.join(OUT, "chain.csv"))
    print(f"Underlying: 252 days, last close {spot:.2f}; chain: {len(chain)} quotes")

    # 2. Research study: rebuild the vol surface and run arbitrage checks.
    surface, breaks = run_all_checks(chain, RATE)
    print(f"Surface: {len(surface)} expiries; arbitrage breaks found: {len(breaks)}")
    for b in breaks:
        print("  BREAK:", b)

    # 3. Strategy simulation: payoffs at expiry for three structures.
    lines = [f"Options Strategy Research — demo report",
             f"Underlying last close: {spot:.2f}",
             f"Chain quotes: {len(chain)}; surface expiries: {sorted(surface)}",
             f"Arbitrage breaks: {len(breaks)}"]
    spots = [round(spot * f, 2) for f in (0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20)]
    straddle = build_straddle(spot, 30, RATE, VOL)
    lines.append("\nLong ATM straddle (30d) P&L at expiry:")
    for s, pnl in payoff_curve(straddle, spots):
        lines.append(f"  spot {s:7.2f} -> P&L {pnl:8.2f}")
    lines.append("\n" + ascii_payoff(straddle, spot * 0.8, spot * 1.2))
    covered = build_covered_call(spot, round(spot * 1.05), RATE, VOL, 30)
    lines.append("\nCovered call (105% strike, 30d) P&L at expiry:")
    for s, pnl in payoff_curve(covered, spots):
        lines.append(f"  spot {s:7.2f} -> P&L {pnl:8.2f}")
    condor = build_iron_condor(spot, round(spot * 0.90), round(spot * 0.95),
                               round(spot * 1.05), round(spot * 1.10), 30, RATE, VOL)
    lines.append("\nIron condor (90/95/105/110, 30d) P&L at expiry:")
    for s, pnl in payoff_curve(condor, spots):
        lines.append(f"  spot {s:7.2f} -> P&L {pnl:8.2f}")

    # 4. Backtest: delta-hedged straddle across the full path.
    results = run_study(prices, expiry_days=30, step=30)
    summary = study_summary(results)
    lines.append(f"\nDelta-hedged straddle study: {summary}")
    for i, r in enumerate(results):
        lines.append(f"  trade {i}: strike {r['strike']}, "
                     f"P&L {r['total_pnl']:.2f}, Sharpe {r['sharpe']:.2f}, "
                     f"max DD {r['max_drawdown']:.2f}")
    write_pnl_csv(results[0]["pnl_series"], os.path.join(OUT, "pnl.csv"))
    with open(os.path.join(OUT, "report.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWrote {OUT}/report.txt, chain.csv, prices.json, pnl.csv")


if __name__ == "__main__":
    main()
