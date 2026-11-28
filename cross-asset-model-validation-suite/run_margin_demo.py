"""Demo: clearing margin, stress testing and backtesting on synthetic data.

Builds a small synthetic cleared-derivatives portfolio (equity index,
rates and crude), computes 99% historical VaR and expected shortfall
from 250 seeded daily returns, runs three stress scenarios, and reports
the margin requirement plus a Kupiec backtest of the VaR.

All data is synthetic and seeded. Nothing here is a real portfolio,
real member, or real OCC margin number.

Usage:  python run_margin_demo.py
"""

import random

from model_validation_suite.margin import (
    backtest_breaches,
    cornish_fisher_var,
    historical_expected_shortfall,
    historical_var,
    kupiec_pof_lr,
    kupiec_pof_pvalue,
    margin_report,
    portfolio_losses,
)

CONFIDENCE = 0.99
N_DAYS = 250
SEED = 20261128


def synthetic_returns(n_days=N_DAYS, seed=SEED):
    """Seeded synthetic daily returns for SPX, rates (UST10) and crude (CL)."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n_days):
        rows.append(
            [
                rng.gauss(-0.0002, 0.012),   # SPX
                rng.gauss(0.0, 0.004),       # UST10 yield proxy
                rng.gauss(0.0001, 0.021),    # CL
            ]
        )
    return rows


def main():
    notional = 10_000_000.0
    weights = [0.5, 0.3, 0.2]
    # Dollar losses on a $10m notional so the VaR leg and the dollar
    # stress leg of the margin are in the same units.
    losses = [loss * notional for loss in portfolio_losses(synthetic_returns(), weights)]
    positions = [
        {"underlying": "SPX", "delta": 2_500_000.0},
        {"underlying": "UST10", "delta": -800_000.0},
        {"underlying": "CL", "delta": 600_000.0},
    ]
    scenarios = [
        {"SPX": -0.05, "UST10": 0.005, "CL": -0.08},   # broad sell-off
        {"SPX": -0.10, "UST10": -0.01, "CL": 0.15},    # equity crash, oil spike
        {"SPX": 0.03, "UST10": 0.02, "CL": -0.12},     # rates shock, oil drop
    ]
    report = margin_report(losses, positions, scenarios, confidence=CONFIDENCE)
    var_series = [report["var"]] * len(losses)
    breaches = backtest_breaches(losses, var_series)
    lr = kupiec_pof_lr(breaches, len(losses), 1.0 - CONFIDENCE)
    pvalue = kupiec_pof_pvalue(breaches, len(losses), 1.0 - CONFIDENCE)
    cf_var = cornish_fisher_var(0.0, 0.012, 0.0, 3.0, CONFIDENCE)

    print("Clearing margin demo (synthetic portfolio, 250 seeded days)")
    print(f"  99% historical VaR:          ${report['var']:,.0f}")
    print(f"  99% expected shortfall:       ${report['expected_shortfall']:,.0f}")
    print(f"  Cornish-Fisher 99% VaR (unit): {cf_var:.4f} (fat-tail adjusted)")
    print(f"  Worst stress loss:            ${report['worst_stress_loss']:,.0f} "
          f"(scenario {report['worst_scenario']})")
    print(f"  Margin requirement:           ${report['margin']:,.0f}")
    print(f"  Backtest: {breaches} breaches in {len(losses)} days "
          f"(expected {(1.0 - CONFIDENCE) * len(losses):.1f})")
    print(f"  Kupiec POF: LR = {lr:.3f}, p-value = {pvalue:.3f}")


if __name__ == "__main__":
    main()
