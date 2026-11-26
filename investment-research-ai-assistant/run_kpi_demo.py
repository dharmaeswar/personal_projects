"""Demo runner: single-stock KPI dashboard and long/short signal backtest."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_assistant.kpi import kpi_report


def main():
    report = kpi_report()
    print("=== Single-stock KPI dashboard (seeded, fictional companies) ===\n")
    for row in report["dashboard"]:
        print(f"{row['company']}: {row['position']} (score {row['signal_score']})")
        print(f"  Revenue growth: {row['latest_revenue_growth_pct']}% YoY | "
              f"Operating margin: {row['latest_operating_margin_pct']}% | "
              f"Alt-data index: {row['latest_alt_index']} "
              f"(momentum {row['alt_momentum_pct']}% over 4Q)")
        print(f"  Next-quarter revenue-growth forecast: "
              f"{row['next_quarter_revenue_growth_forecast_pct']}% "
              f"(slope {row['revenue_trend_slope']}, R^2 "
              f"{row['revenue_forecast_r_squared']})")
        for kind in ("revenue_inflections", "margin_inflections"):
            for flag in row[kind]:
                print(f"  Inflection ({kind}): quarter "
                      f"{report['quarters'][flag['index']]} "
                      f"{flag['direction']} (z={flag['z']})")
        print()
    backtest = report["backtest"]
    print("=== KPI-signal backtest (long top score, short bottom score) ===")
    for trade in backtest["trades"]:
        print(f"  Formed {trade['formation_quarter']}, held {trade['holding_quarter']}: "
              f"long {trade['long']} ({trade['long_return_pct']}%), "
              f"short {trade['short']} ({trade['short_return_pct']}%), "
              f"net {trade['net_return_pct']}%")
    print(f"Trades: {backtest['n_trades']} | Hit rate: {backtest['hit_rate']} | "
          f"Mean quarterly return: {backtest['mean_quarterly_return_pct']}% | "
          f"Total return: {backtest['total_return_pct']}%")
    report_path = "kpi_report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
