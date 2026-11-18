# Robotaxi Performance Telemetry

A portfolio project for a Data Scientist, Robotaxi Performance &
Capability role. It analyses synthetic robotaxi fleet telemetry the
way a driverless-readiness team would: build performance metrics and
baselines across software releases, quantify uncertainty around rare
intervention events, and judge whether a release-over-release change
is a real improvement or noise — all in plain Python (standard
library only).

**All data is synthetic and seeded.** No real vehicles, trips,
operators, or passengers are involved. Nothing here describes a real
fleet, a real safety record, or a real product decision. The
intervention types mirror the public job description (safety-critical
interventions, unnecessary stops, stuck scenarios, manoeuvre
execution); the numbers are invented for demonstration only.

## What it does

- **Generate** — 1,200 synthetic trips (seed 42) across three
  software releases (2026.09–2026.11), three road types, and 40
  vehicles: miles, duration, mission outcome, interventions by type,
  recovery time, remote assistance, and pickup delay.
- **Measure** — readiness KPIs: interventions per 1,000 miles
  (overall and by type), mission completion rate, mean recovery time,
  remote-assistance rate, mean pickup delay, and a vehicle-availability
  proxy. KPIs are cut by release and by road type.
- **Quantify uncertainty** — exact Poisson confidence intervals for
  intervention rates, because safety-critical interventions are rare
  events and a point estimate alone is not evidence.
- **Compare releases** — a two-sample Poisson rate test (conditional
  binomial) with a two-sided p-value, so a drop in the intervention
  rate is reported as significant or as noise.

## Results of a run (`python run_analysis.py`)

```
Trips: 1,200 | Miles: 18,088.2
Interventions per 1,000 miles: 6.8 (95% CI 5.60–8.05)
  safety-critical 0.442 | unnecessary stops 3.096
  stuck scenarios 1.106 | manoeuvre execution 2.156
Mission completion: 97.17% | Mean recovery: 14.29 min
Remote assistance: 6.0% | Mean pickup delay: 3.0 min
Vehicle availability proxy: 90.08%
By release (interventions/1k miles): 2026.09: 8.682 | 2026.10: 6.396 | 2026.11: 5.194
Release comparisons: 2026.09 vs 2026.10 p=0.1746 (not significant)
                     2026.10 vs 2026.11 p=0.399  (not significant)
```

The honest read: intervention rates fall across releases in this
sample, but neither step clears the 95% bar — more miles are needed
before calling it an improvement. Urban roads intervene most
(9.15/1k miles) and highways least (4.35/1k miles).

## Run it

```bash
python -m pytest tests/ -q        # 18 tests
python run_analysis.py            # writes report.md and report.json
```

## Files

- `robotaxi_telemetry/data.py` — seeded synthetic trip generator
- `robotaxi_telemetry/metrics.py` — readiness KPIs
- `robotaxi_telemetry/stats.py` — exact Poisson CI, rate comparison
- `run_analysis.py` — end-to-end analysis, Markdown + JSON report
- `tests/test_robotaxi.py` — 18 tests
