# Card-Issuing Deal Pricing Model

A local, end-to-end commercial-finance toolkit built in Python (standard
library only) — a portfolio project matching Marqeta's **Senior Commercial
Finance Analyst, Pricing & Deal Modeling** role: the FP&A work of turning
customer performance data into forecasts, deal recommendations, and clear
explanations of how the business is doing.

**All data is synthetic and seeded in code.** No real company or customer
data appears anywhere, and nothing here was used in production or by any
real company. It is not a Marqeta system and claims no affiliation.

## What it does

| Module | Marqeta JD item |
|---|---|
| `deal_pricing/economics.py` | **Customer economics** — interchange revenue, network fees, bank-partner cost, processing cost and fixed cost per customer-month, to gross profit and margin, in Decimal money rounded to cents |
| `deal_pricing/forecast.py` | **Forecasting** — from top-line drivers (active cards, growth, txns per card, avg ticket) through to gross profit, with base / upside / downside scenarios |
| `deal_pricing/deal_model.py` | **Deal modeling** — price proposed terms vs current terms: incremental gross profit, margin in bps, break-even TPV, and +/-10% / +/-20% volume sensitivity |
| `deal_pricing/variance.py` | **Variance commentary** — decompose actual-vs-forecast profit into volume, take-rate and fixed-cost drivers that sum exactly to the total, plus a plain-language paragraph for the monthly deck |
| `deal_pricing/reconcile.py` | **SQL reconciliation** — load monthly economics into SQLite and check Python totals against a SQL `GROUP BY`; the run fails on any gap over $0.01 |
| `deal_pricing/report.py` | **Deck support files** — Excel-ready CSVs (monthly economics, 6-month forecast) and a plain-text stakeholder summary |
| `run_deal_model.py` | End-to-end demo: 3 customers, 6 months of actuals, forecast, a deal in negotiation, variance commentary, reconciliation, reports |

## How it differs from the other projects in this repo

- `pricing-risk-analytics-library` prices derivatives for a trading book
  (Black-Scholes, PDE solvers, VaR). This prices **commercial deals** for
  card-issuing customers: interchange, network and bank-partner economics,
  not option Greeks.
- `client-analytics-reporting-suite` reports client KPIs and trends. This
  adds the missing half for this role: **forecasting and deal pricing**
  (break-even TPV, sensitivity, scenario forecasts) and variance
  commentary tied to gross profit.
- `sales-compensation-calculation-engine` calculates rep pay from closed
  deals. This prices the **customer deal itself** before it is signed.
- `subscription-billing-event-platform` models subscription billing events.
  This models **card volume economics** (TPV, interchange bps, per-txn
  fees), a different revenue model entirely.

## Demo results (`python3 run_deal_model.py`)

- Portfolio (6 customer-months): TPV $26,830,000.00, interchange
  $379,765.00, gross profit $209,651.00 (55.21% margin), 561,500 txns.
- Northwind 6-month gross profit: base $244,220.05, upside $276,103.83,
  downside $212,336.29.
- Helios renewal as priced (150 bps interchange, 24 bps bank share):
  **loses $2,040.00/month** (-6.00 bps of TPV) at committed volume and
  needs $3,592,291.67 TPV to break even — the model says renegotiate,
  not sign. Sensitivity shows the loss grows with volume, so volume
  alone cannot rescue this deal.
- Variance commentary for October 2026 is generated per customer with
  drivers that sum exactly to the total variance.
- Reconciliation: Python totals match the SQL `GROUP BY` totals.

## How to run

```bash
pip install -r requirements.txt   # pytest only
python3 -m pytest tests/ -q       # 12 tests
python3 run_deal_model.py         # demo + reports/ (CSV, JSON, summary)
```

## Honest scope

- Runs locally on SQLite, not Snowflake; the SQL is standard
  `GROUP BY` aggregation, and the reconciliation discipline is the same
  one the JD asks for (numbers in the deck tie back to the data).
- No dbt models, no Sigma dashboards, no live AI calls: the variance
  commentary is deterministic text from the decomposed drivers, and the
  forecast is a documented driver-based method, not a fitted model.
- Interchange / network / bank-partner bps in the demo are illustrative
  round numbers, not Marqeta's real pricing.
