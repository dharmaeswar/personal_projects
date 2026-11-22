"""Demo: run the research report and print the summary."""

from sys_signal_research.__main__ import run_research

if __name__ == "__main__":
    report = run_research()
    print(f"Portfolio Sharpe {report['portfolio_metrics']['sharpe']:.2f}")
    print(f"CAGR {report['portfolio_metrics']['cagr']:.2%}")
    print(f"Max drawdown {report['portfolio_metrics']['max_drawdown']:.2%}")
    print("Walk-forward (ES momentum):")
    for row in report["walk_forward_es_momentum"]:
        print(
            f"  fold {row['fold']}: in-sample Sharpe {row['in_sample_sharpe']}, "
            f"out-of-sample Sharpe {row['out_of_sample_sharpe']}"
        )
