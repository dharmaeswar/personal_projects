# Subscriber Units Cabled Analytics

A portfolio project for a **Comcast Analyst 4, Subscriber Data Analytics**
role (Req R449420): national Units Cabled (UC) reporting, a rolling 120-day
forecast, reconciliation across Salesforce / deployment-tracker / billing
feeds, bulk-master event impact analysis, and scorecard reporting.

**All data is synthetic and seeded in code (seed 42).** No real Comcast,
Xfinity, or subscriber data appears anywhere, and nothing here ran in
production or at any real company.

## Problem statement

A national Units Cabled analyst owns the number leadership plans around —
daily, weekly, and monthly UC reporting with actuals, forecast, variance,
and trends — but the number comes from three feeds that disagree:
Salesforce reporting, deployment trackers, and billing systems. Bulk
master activations, de-bulks, and disconnections move the count in steps
the forecast cannot see coming, and a stale or double-counted feed ships
a wrong number to an operational review unless someone reconciles first.

## What it does

| Module | JD responsibility it covers |
|---|---|
| `uc_analytics/reporting.py` | Daily / weekly / monthly UC reporting: actuals, forecast, variance in units and %, period-over-period trend. Partial periods are excluded so a mid-month actual is never compared with a full-month forecast. |
| `uc_analytics/forecast.py` | Rolling 120-day forecast (trailing moving average + linear trend + day-of-week factor) with a replayed backtest so accuracy is measured, not asserted. |
| `uc_analytics/reconcile.py` | Cross-source reconciliation on (date, community): flags value mismatches beyond tolerance and rows missing from any feed, each with a category pointing follow-up at the right partner. |
| `uc_analytics/impact.py` | Bulk-master event impact: before/after mean daily UC around each activation, de-bulk, and disconnection, checked against the event's stated unit count. |
| `uc_analytics/scorecard.py` | National scorecard (actual vs forecast by region/period), a variance watchlist, and an executive summary in Markdown. |
| `run_uc.py` | End-to-end demo: seeds data, prints the scorecard, forecast, breaks, and event impacts, and writes `outputs/monthly_scorecard.csv` and `outputs/executive_summary.md`. |

## Results (measured on the seeded data)

- **Coverage:** 180 days (2026-05-25 to 2026-11-20), 11 communities in
  3 regions (Philadelphia, Dacula, Englewood), 1,140,684 unit-days.
- **Forecast backtest** (28-day horizon, 18 origins per region):
  Philadelphia MAPE 2.27%, Dacula 1.49%, Englewood 1.43%.
  120-day forecast totals: Philadelphia 355,661; Dacula 215,257;
  Englewood 244,478 units.
- **Reconciliation:** 10 breaks found — 7 days missing from the billing
  feed (DAC-203, Aug 3–9), 2 Salesforce mismatches of −118 units
  (PHL-102, Sep 14–15 — Salesforce lagged the bulk activation by two
  days), 1 deployment-tracker mismatch of +210 units (ENG-303, Oct 5 —
  double-counted day).
- **Bulk-master impacts** (14-day before/after means): activation
  PHL-102 expected +118, observed +123.9 (unexplained +5.9); de-bulk
  DAC-201 expected −64, observed −54.1 (unexplained +9.9); disconnection
  ENG-301 expected −92, observed −81.5 (unexplained +10.5); activation
  PHL-104 expected +57, observed +60.5 (unexplained +3.5). Residuals are
  trend and noise; no event is unexplained by more than ~11 units/day.
- **Variance watchlist:** the largest monthly variance is Philadelphia
  Sep (+8.17%) and Oct (+9.83%) — the forecast snapshots predate the two
  bulk activations, so the investigation points at the activations, not
  at a reporting error.

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_uc.py
```

21 pytest tests pass. The test suite pins the seeded breaks exactly
(7 missing billing days, 2 Salesforce mismatches of −118, 1 deployment
mismatch of +210), so any change to the seed or the tolerance breaks a
test instead of silently changing the story.
