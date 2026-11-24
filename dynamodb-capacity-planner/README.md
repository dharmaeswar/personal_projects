# DynamoDB Capacity Planner

Demand forecasting, capacity planning, quota/entitlement enforcement and
fleet-event simulation for a distributed NoSQL-style database — the same
class of problem the AWS DynamoDB Capacity & Customer Entitlement team
works on: forecast demand across regions, plan and place capacity across
the fleet, and manage the limits and entitlements that decide how far each
customer can scale.

All data is synthetic and generated locally. Nothing here claims production
DynamoDB use. Per-partition limits (3,000 RCU / 1,000 WCU / 10 GB) are
planning assumptions from public DynamoDB documentation.

## What it does

- **Forecast** (`capplanner/forecast.py`) — least-squares fit of trend plus
  daily and weekly seasonality to an hourly request-rate series, with a
  prediction band from the residual spread. Finds the forecast peak.
- **Plan** (`capplanner/capacity.py`) — converts a forecast peak (reads and
  writes per second), item size and stored data into required partitions,
  provisioned RCU/WCU, headroom and a rough monthly cost.
- **Enforce** (`capplanner/entitlement.py`) — per-customer quota ledger with
  a token-bucket admission check (rate and storage quotas) and limit-increase
  requests approved only when the fleet has headroom for them.
- **Simulate** (`capplanner/fleet.py`) — runs a multi-region fleet through a
  demand event (e.g. a Prime Day-style spike), emits scaling actions when the
  forecast outruns provisioned capacity, and reports throttled hours and
  whether capacity was ready before the peak.

## Run it

```bash
pip install -r requirements.txt
python run_demo.py
python -m capplanner.cli forecast --ahead 24
python -m capplanner.cli plan --reads 1200 --writes 400 --item-kb 2 --storage-gb 40
python -m capplanner.cli enforce --customer customer-a --requests 500
python -m capplanner.cli simulate --partitions 2
```

## Tests

```bash
python -m pytest tests/ -q
```

## Project layout

```
capplanner/
  forecast.py      trend + seasonality demand forecasting
  capacity.py      partition / RCU / WCU / cost planning
  entitlement.py   quota ledger, token bucket, limit increases
  fleet.py         multi-region demand-event simulation
  report.py        text and JSON reports
  cli.py           forecast / plan / enforce / simulate commands
tests/             pytest suite (forecast, capacity, entitlement, fleet, CLI)
run_demo.py        end-to-end demo on synthetic data
```
