"""Run the full investment-model governance validation and write a report.

Usage:
    python -m investment_governance [--out validation_report.json]

Runs, on seeded synthetic data:
  1. Alpha-signal validation (IC, IC decay, turnover, hit rate).
  2. Portfolio-construction validation (min-variance vs equal weight).
  3. Risk-model backtest (historical VaR, Kupiec, Christoffersen).
  4. Asset-allocation validation (risk parity, diversification, drawdown).
  5. Model-inventory governance gaps and a sample validation report.
"""

import argparse
import json

import numpy as np

from . import allocation, data, governance, portfolio, risk, signals


def run_validation(seed=42):
    market = data.synthetic_market(seed=seed)
    returns = market["returns"]
    sig = market["signals"]
    fwd = market["forward_returns"]
    cov = market["cov"]
    mu = market["expected_returns"]

    # 1. Alpha signal: cross-sectional IC on the last 200 days.
    sig_flat = sig[:-1].ravel()
    fwd_flat = fwd[:-1].ravel()
    ic_by_horizon = signals.ic_decay(
        sig_flat,
        {"1d": fwd_flat, "5d": np.roll(fwd_flat, -4), "20d": np.roll(fwd_flat, -19)},
    )
    signal_results = {
        "spearman_ic_1d": round(signals.spearman_ic(sig_flat, fwd_flat), 4),
        "pearson_ic_1d": round(signals.pearson_ic(sig_flat, fwd_flat), 4),
        "ic_by_horizon": {k: round(v, 4) for k, v in ic_by_horizon.items()},
        "hit_rate": round(signals.hit_rate(sig_flat, fwd_flat), 4),
    }

    # 2. Portfolio construction: min-variance with a 40% name cap.
    w_mv = portfolio.min_variance_weights(cov, cap=0.40)
    w_eq = np.full(len(mu), 1.0 / len(mu))
    portfolio_results = {
        "min_variance_weights": {a: round(float(w), 4) for a, w in zip(market["assets"], w_mv)},
        "min_variance_vol": round(portfolio.portfolio_volatility(w_mv, cov), 4),
        "equal_weight_vol": round(portfolio.portfolio_volatility(w_eq, cov), 4),
        "min_variance_sharpe": round(portfolio.sharpe_ratio(w_mv, mu, cov), 4),
        "herfindahl": round(portfolio.herfindahl(w_mv), 4),
        "checks": portfolio.validate_portfolio(w_mv, cov, mu, cap=0.40),
    }

    # 3. Risk model: 95% VaR backtest on the equal-weight portfolio.
    port_returns = returns @ w_eq
    var_series = np.full(len(port_returns), risk.historical_var(port_returns, 0.05))
    risk_results = risk.backtest_var(port_returns, var_series, alpha=0.05)
    risk_results["var_95"] = round(float(var_series[0]), 4)
    risk_results["expected_shortfall_95"] = round(
        risk.expected_shortfall(port_returns, 0.05), 4
    )

    # 4. Asset allocation: risk parity, diversification, drawdown.
    w_rp = allocation.risk_parity_weights(cov)
    vols = np.sqrt(np.diag(cov))
    cum = np.cumprod(1.0 + returns @ w_rp)
    allocation_results = {
        "risk_parity_weights": {a: round(float(w), 4) for a, w in zip(market["assets"], w_rp)},
        "risk_contributions": {
            a: round(float(c), 4)
            for a, c in zip(market["assets"], allocation.risk_contributions(w_rp, cov))
        },
        "diversification_ratio": round(allocation.diversification_ratio(w_rp, vols, cov), 4),
        "max_drawdown": round(allocation.max_drawdown(cum), 4),
    }

    # 5. Governance: inventory gaps + a sample validation report.
    register = [
        governance.ModelRecord(
            "IMG-ALPHA-01", "Cross-asset momentum signal", "alpha_signal",
            "Quant Research", "in_use", "high", 14,
        ),
        governance.ModelRecord(
            "IMG-OPT-02", "Mean-variance portfolio optimizer", "portfolio_optimizer",
            "Portfolio Construction", "in_use", "high", 6,
            findings=[governance.Finding("Turnover limit undocumented", "Medium",
                                          "No turnover cap in the methodology note.")],
        ),
        governance.ModelRecord(
            "IMG-VAR-03", "Historical VaR risk model", "risk_var",
            "Risk Analytics", "in_use", "medium", 20,
        ),
        governance.ModelRecord(
            "IMG-ALLOC-04", "Strategic asset allocation", "asset_allocation",
            "", "approved", "low", 26,
        ),
    ]
    gaps = governance.inventory_gaps(register)
    sample = governance.build_validation_report(
        register[1],
        register[1].findings,
        {c: True for c in governance.effective_challenge_checklist()},
    )
    governance_results = {
        "inventory_gaps": gaps,
        "sample_validation_report": sample,
    }

    report = {
        "seed": seed,
        "signal_validation": signal_results,
        "portfolio_validation": portfolio_results,
        "risk_backtest": risk_results,
        "allocation_validation": allocation_results,
        "governance": governance_results,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description="Investment model governance validation")
    parser.add_argument("--out", default="validation_report.json")
    args = parser.parse_args()
    report = run_validation()
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2))
    print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
