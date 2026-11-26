"""End-to-end demo: seed data, report, forecast, reconcile, scorecard.

Usage: python run_uc.py [--out-dir outputs]
"""

import argparse
import csv
import os

from uc_analytics import forecast, impact, reconcile, reporting, scorecard, seed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="outputs")
    args = parser.parse_args()
    data = seed.generate()

    monthly = reporting.aggregate(data["actuals"], "monthly")
    print(f"Months reported: {len(monthly)}; "
          f"total unit-days: {sum(r['units'] for r in monthly):,}")

    card = scorecard.national_scorecard(data["actuals"], data["forecasts"], "monthly")
    watch = scorecard.variance_watchlist(card)
    print(f"Scorecard rows: {len(card)}; variance watchlist (>|2%|): {len(watch)}")
    for row in watch:
        print(f"  {row['period_start']} {row['region']}: actual {row['actual']:,} "
              f"vs forecast {row['forecast']:,} ({row['variance_pct']:+.2f}%)")

    for region in seed.REGIONS:
        series = forecast.daily_region_totals(data["actuals"], region)
        fc = forecast.forecast_120(series)
        bt = forecast.backtest(series)
        print(f"{region}: 120-day forecast total {sum(u for _d, u in fc):,} units; "
              f"backtest MAPE {bt['mean_mape_pct']}% over {len(bt['origins'])} origins")

    breaks = reconcile.reconcile(data["actuals"], data["salesforce"],
                                 data["deployment"], data["billing"])
    print(f"Reconciliation breaks: {len(breaks)} — {reconcile.summarize(breaks)['by_category']}")

    for event in data["bulk_events"]:
        res = impact.event_impact(data["actuals"], event)
        print(f"{res['event_id']} {res['type']} {res['community']}: "
              f"expected {res['expected_change']:+d}, observed "
              f"{res['observed_change']:+.1f}, unexplained {res['unexplained']:+.1f}")

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "monthly_scorecard.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["period_start", "region", "units", "actual",
                                          "forecast", "variance", "variance_pct"])
        w.writeheader()
        w.writerows(card)
    with open(os.path.join(args.out_dir, "executive_summary.md"), "w") as f:
        f.write(scorecard.executive_summary(data))
    print(f"Wrote {args.out_dir}/monthly_scorecard.csv and "
          f"{args.out_dir}/executive_summary.md")


if __name__ == "__main__":
    main()
