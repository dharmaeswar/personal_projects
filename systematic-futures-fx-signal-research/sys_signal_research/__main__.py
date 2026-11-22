"""Run the full signal-research report and write it as JSON.

Usage:
    PYTHONPATH=. python -m sys_signal_research --out research_report.json
"""

import argparse
import json

from .backtest import apply_vol_target, backtest, diversification_stats, portfolio_metrics
from .data import daily_returns, generate_carry, generate_prices
from .portfolio import build_portfolio
from .robustness import cost_sensitivity, signal_decay, sim_vs_actual_gap, walk_forward
from .signals import (
    carry_signal,
    combine_signals,
    mean_reversion,
    moving_average_crossover,
    time_series_momentum,
)

FX_PAIRS = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]


def run_research(seed=42):
    prices = generate_prices(seed=seed)
    carry = generate_carry(prices)
    rets = daily_returns(prices)

    # One combined signal per instrument: trend + crossover for futures,
    # trend + carry for FX, with a small mean-reversion sleeve everywhere.
    strategy_results = {}
    for name in prices.columns:
        if name in FX_PAIRS:
            sig = combine_signals(
                {
                    "momentum": time_series_momentum(prices[name]),
                    "carry": carry_signal(carry[name]),
                    "reversion": mean_reversion(prices[name]),
                },
                weights={"momentum": 0.5, "carry": 0.3, "reversion": 0.2},
            )
        else:
            sig = combine_signals(
                {
                    "momentum": time_series_momentum(prices[name]),
                    "crossover": moving_average_crossover(prices[name]),
                    "reversion": mean_reversion(prices[name]),
                },
                weights={"momentum": 0.5, "crossover": 0.3, "reversion": 0.2},
            )
        sig = apply_vol_target(sig, rets[name], target_vol=0.10)
        strategy_results[name] = backtest(prices[name], sig, cost_bps=2.0)

    port_rets, weights = build_portfolio(strategy_results)
    equity = (1.0 + port_rets).cumprod()
    metrics = portfolio_metrics(equity)
    diversification = diversification_stats(
        __import__("pandas").DataFrame({n: df["return"] for n, df in strategy_results.items()})
    )

    # Robustness checks on the equity-index trend signal (ES momentum).
    es_momentum = time_series_momentum(prices["ES"])
    wf = walk_forward(
        prices["ES"],
        lambda p, lookback=252: time_series_momentum(p, lookback=lookback),
        param_grid=[{"lookback": 63}, {"lookback": 126}, {"lookback": 252}],
        n_folds=4,
        cost_bps=2.0,
    )
    costs = cost_sensitivity(prices["ES"], es_momentum)
    decay = signal_decay(prices["ES"], es_momentum, max_lag=10)
    gap = sim_vs_actual_gap(strategy_results["ES"])

    return {
        "instruments": list(prices.columns),
        "n_days": int(len(prices)),
        "portfolio_metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()},
        "risk_parity_weights": {k: round(float(v), 4) for k, v in weights.items()},
        "diversification": diversification,
        "walk_forward_es_momentum": wf,
        "cost_sensitivity_es_momentum": costs,
        "signal_decay_es_momentum": decay,
        "sim_vs_actual_gap_es": gap,
    }


def main():
    parser = argparse.ArgumentParser(description="Systematic futures & FX signal research report")
    parser.add_argument("--out", default="research_report.json")
    args = parser.parse_args()
    report = run_research()
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    m = report["portfolio_metrics"]
    print(f"Instruments: {len(report['instruments'])} over {report['n_days']} days")
    print(f"Portfolio Sharpe {m['sharpe']:.2f} | CAGR {m['cagr']:.2%} | max drawdown {m['max_drawdown']:.2%}")
    print(f"Avg strategy correlation: {report['diversification']['avg_correlation']:.2f}")
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
