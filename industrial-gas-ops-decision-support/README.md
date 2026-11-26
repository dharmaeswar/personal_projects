# Industrial Gas Operations Decision-Support

A full-stack decision-support tool for industrial-gas production and
distribution: a Python backend with a SQLite relational store, a
trend + seasonal demand forecaster, delivery-route optimization,
Monte Carlo stockout simulation, and a single-page browser dashboard
that calls the API.

Built as a portfolio project for the Linde — Full Stack Data Scientist
(Tonawanda, NY, req34741) application.

**Demo project. All data is synthetic and seeded.** Plants, customers,
locations and demand are invented test data; nothing here describes a
real Linde plant, customer, contract or delivery, and no production
deployment or customer use is claimed.

## Problem statement

An industrial-gas supplier has to answer three questions every day:
how much will each customer need next week, which plant should serve
each customer, and in what order should one truck visit them — while
keeping enough stock on hand that a demand spike does not stock a
customer out. This tool answers all three from one store, behind one
web app.

## What it does

- **Data** (`gas_ops/data.py`) — 5 plants (oxygen, nitrogen, argon,
  hydrogen) and 12 customers on a kilometre grid around Tonawanda, NY,
  with 90 days of seeded daily demand per customer (base level, slow
  trend, weekly seasonality, Gaussian noise).
- **Relational store** (`gas_ops/store.py`) — SQLite tables for plants,
  customers, demand history, inventory and deliveries, with indexes on
  every join/filter column. `explain_history_lookup` shows the planner
  using the index for customer-history reads.
- **Forecast** (`gas_ops/forecast.py`) — trend (least squares) +
  7-day moving average + weekly seasonal factor, no look-ahead.
  Time-based backtest (train 60 days, test 30): mean MAPE **6.32%**
  across all 12 customers vs **11.24%** for a naive last-value
  baseline; Lakeshore Steel Mill (C-01) backtest 6.85% vs 14.25%.
- **Route optimization** (`gas_ops/optimize.py`) — nearest-neighbour
  tour improved with 2-opt swaps, always at least as good as the
  greedy tour. All six oxygen customers from Tonawanda: **86.36 km**
  optimized vs **120.77 km** in the given order, **28.5% saved**.
  Plant assignment is greedy by distance subject to same-product and
  remaining-capacity checks.
- **Simulation** (`gas_ops/simulate.py`) — Monte Carlo (2,000 seeded
  Normal draws) stockout probability at a given inventory, plus safety
  stock for a target service level. Example: C-01 at 90 t on hand has
  an 87.5% stockout probability (mean demand 99.5 t/day); 95%
  service-level safety stock is 13.96 t.
- **Full-stack service** (`gas_ops/api.py` + `gas_ops/frontend.html`)
  — a Python HTTP server serving a single-page dashboard (plain
  HTML/CSS/JavaScript, `fetch()` calls, no front-end framework) and
  JSON endpoints: `/api/dashboard`, `/api/forecast`,
  `/api/route` (POST), `/api/simulate`, `/health`. Planned routes are
  persisted as deliveries in SQLite and shown on the dashboard.

## Skills used

Only skills Dharma has verified: Python (standard library only),
SQLite and SQL, HTML, CSS, JavaScript, REST APIs, JSON, pytest,
Linux. This project does **not** claim React, Angular, Node.js, a
production database, or a production deployment — the frontend is
plain JavaScript, the store is SQLite, and the server is the Python
standard-library HTTP server.

## Run it

```bash
pip install -r requirements.txt   # pytest only
python -m pytest -q               # 11 tests, all passing
python run_service.py             # listens on http://127.0.0.1:8000
```

Open http://127.0.0.1:8000 in a browser: plant inventory, a 7-day
forecast picker, a route planner (pick a plant and customers), and a
stockout simulator.

## Assumptions and limitations

- Demand is modelled as Normal around a trend + weekly seasonal mean.
  Real demand is skewed and has spikes this model does not reproduce;
  the simulation is a planning aid, not a guarantee.
- Distances are straight-line kilometres on a flat grid, not road
  distances; route savings are relative to that grid.
- One SQLite connection is shared behind a per-request lock; the
  service is a demo, not built for concurrent production load.
