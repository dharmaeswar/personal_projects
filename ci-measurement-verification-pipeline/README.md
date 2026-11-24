# C&I Measurement & Verification Pipeline

A demand-response measurement and verification (M&V) pipeline for
commercial and industrial customers: raw meter readings go through
baselines, event performance and payments to the reports operations
teams and partners rely on.

## The problem

A demand-response program pays factories, offices and retail sites to
cut power when the grid needs it. To pay them fairly the platform must
prove, for each event, how much each site actually curtailed — the
difference between what the site *would* have used (the baseline) and
what its meter recorded. Meter data is messy: duplicate reads, late
arrivals, gaps, bad timestamps and time-zone mixes. A payment computed
from dirty data is a payment that cannot be explained months later.

## What it does

Layered models, in the shape of a dbt project (staging → intermediate →
marts), implemented as plain Python modules over SQLite so the whole
pipeline runs locally with no warehouse:

- **Staging** (`mv_pipeline/staging.py`) — dedupes readings by
  (site, timestamp), quarantines negative or missing kW values,
  normalises every timestamp to UTC, and flags late arrivals. A re-run
  of the same batch is a no-op: loads are idempotent, never double-count.
- **Baseline** (`mv_pipeline/baseline.py`) — for each site and event,
  the baseline for a 15-minute interval is the mean of that same
  interval across the 10 most recent eligible non-event days (same
  day-of-week preferred). Days with gaps are excluded from the pool.
- **Performance** (`mv_pipeline/performance.py`) — event performance is
  baseline minus actual metered kW per interval; curtailed energy is
  the sum over the event window. Payment is curtailed kW × the program
  rate, with the per-interval math kept so any payment can be traced
  back to the readings that produced it.
- **Data quality** (`mv_pipeline/quality.py`) — checks for interval
  gaps, duplicate reads, late arrivals, negative values and unknown
  site ids, reported per batch with counts and examples.
- **Marts** (`mv_pipeline/marts.py`) — `mart_site_event_summary` (one
  row per site per event: baseline kW, actual kW, curtailed kW/kWh,
  payment) and `mart_payments` (the payment report).

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py            # runs the seeded event, writes report.json
python -m pytest -q               # 16 tests
```

## Results (seeded, reproducible)

- Seeded event: 3 sites, 15-minute intervals, 10 baseline days.
- Staging: 3,177 raw readings → 3,168 staged, 6 duplicates removed,
  3 negative readings quarantined, 2 late arrivals flagged.
- Event performance: site A curtailed 41.16 kW on average across the
  2-hour window (82.33 kWh), site B 18.99 kW (37.98 kWh), site C 0.72 kW
  (1.44 kWh — baseline noise only, no real curtailment).
- Payments: $411.65 + $189.90 + $7.20 = **$608.75** at $5.00 per
  curtailed kWh, fully traceable to per-interval baseline and meter rows.
- Re-running the same batch stages 0 new rows: loads are idempotent.
- Tests: **16 pytest tests, all passing**.

## Notes and limits

- **All data is synthetic and seeded.** Sites, meters, readings and
  events are invented for this pipeline; no real utility, customer or
  meter data is used.
- The layered models mirror a dbt project (staging / intermediate /
  marts, incremental loads, data tests) but run on SQLite locally —
  this is a portfolio pipeline, not a claim of production Snowflake or
  dbt work.
- Baseline method is the standard 10-of-10 same-interval average used
  in demand-response M&V; weather adjustment is out of scope and noted
  as a gap in the report.
