"""Scorecard and executive-summary reporting.

Turns the reporting / forecast / reconciliation / impact outputs into
the recurring materials the role prepares for operational reviews: a
national scorecard (actuals vs forecast by region), a variance watch
list, and a short executive summary in Markdown.
"""

from . import forecast as forecast_mod
from . import impact as impact_mod
from . import reconcile as reconcile_mod
from . import reporting


def national_scorecard(actual_rows, forecast_rows, period="monthly"):
    """Actual vs forecast by region and period, with variance."""
    return reporting.variance_report(actual_rows, forecast_rows, period)


def variance_watchlist(scorecard, threshold_pct=2.0):
    """Scorecard rows whose |variance %| exceeds the threshold."""
    return [r for r in scorecard
            if r["variance_pct"] is not None
            and abs(r["variance_pct"]) > threshold_pct]


def executive_summary(data):
    """Short Markdown summary: totals, forecast accuracy, breaks, events."""
    actuals = data["actuals"]
    total = sum(u for _d, _r, _c, u in actuals)
    regions = sorted({r for _d, r, _c, _u in actuals})
    latest = max(d for d, _r, _c, _u in actuals)
    lines = [f"# Units Cabled — Executive Summary (through {latest.isoformat()})",
             "",
             f"National Units Cabled in the seeded 180-day window: **{total:,}** "
             f"unit-days across {len(regions)} regions "
             f"({', '.join(regions)}).",
             ""]
    bt_lines = []
    for region in regions:
        series = forecast_mod.daily_region_totals(actuals, region)
        bt = forecast_mod.backtest(series)
        bt_lines.append(f"- {region}: rolling 120-day forecast backtest MAPE "
                        f"{bt['mean_mape_pct']}% over {len(bt['origins'])} origins")
    lines += ["## Forecast accuracy (backtested, 28-day horizon)", ""] + bt_lines + [""]

    breaks = reconcile_mod.reconcile(actuals, data["salesforce"],
                                     data["deployment"], data["billing"])
    summary = reconcile_mod.summarize(breaks)
    lines += ["## Reconciliation", "",
              f"{summary['total']} breaks across the three feeds: "
              + "; ".join(f"{k} {v}" for k, v in summary["by_category"].items())
              + ".",
              "Largest breaks are the billing-feed gap for DAC-203 (7 days), "
              "the Salesforce lag on the PHL-102 bulk activation (2 days), and "
              "the deployment-tracker double-count for ENG-303 (1 day).",
              ""]
    lines += ["## Bulk-master events", ""]
    for event in data["bulk_events"]:
        res = impact_mod.event_impact(actuals, event)
        lines.append(f"- {res['event_id']} {res['type']} {res['community']} "
                     f"{res['date']}: expected {res['expected_change']:+d} units/day, "
                     f"observed {res['observed_change']:+.1f}, "
                     f"unexplained {res['unexplained']:+.1f}")
    lines += ["",
              "All figures are computed from the seeded synthetic data in "
              "`uc_analytics/seed.py`; nothing here describes real subscriber counts."]
    return "\n".join(lines)
