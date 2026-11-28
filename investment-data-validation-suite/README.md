# Investment Data Validation Suite

Validates the investment data an Investment Data Management Operations
team owns — security master, trade, and yield data — the way a second-line
data-quality reviewer would: identifier checks, completeness, date logic,
ranges, referential integrity, freshness, and reconciliation of a legacy
extract against the new investment data warehouse.

**All data is synthetic and seeded.** No real issuer, security, trade, or
yield data is used, and nothing here is a claim about any real institution.

## What it validates

- **Security master** (`security_master.py`): CUSIP check digit, ISIN
  Luhn check digit, required-field completeness, duplicate security ids
  and CUSIPs, maturity after issue date, coupon 0–20%, positive face
  value, known asset class and currency, status consistent with maturity.
- **Trades** (`trades.py`): required fields, duplicate trade ids, every
  trade's security exists in the security master, settlement on or after
  the trade date within a 5-day lag, no future-dated trades, positive
  quantity and price, BUY/SELL side.
- **Yield curve** (`yields.py`): every expected tenor present (1M–30Y),
  yields in a sane range, points stamped with today's date (no stale
  data), day-over-day moves within 50bp, and a curve-inversion warning.
- **Warehouse reconciliation** (`warehouse.py`): legacy extract vs new
  investment data warehouse — row counts, key coverage both ways,
  per-security market value and price, and total market value within
  0.01%.

## Dataset onboarding — Cubist Data Services work

A second half, added for the Point72 — Data Scientist, Cubist Data
Services application: onboarding novel datasets the way a systematic
data-services team does it.

- **Novel datasets** (`data.py`, `build_novel_datasets`): three vendor
  feeds with different shapes — ESG scores, corporate actions, FX spot
  rates — each with one planted defect.
- **Profiling** (`dataset_onboarding.py`, `profile_dataset`): infers each
  column's type, completeness and distinct counts, and the earliest and
  latest as-of dates in the feed.
- **Registry** (`register_dataset`): a dataset moves PROPOSED →
  PROFILED → VALIDATED → LIVE one step at a time; skipping a step
  raises an error, so unvalidated data never reaches production.
- **Features** (`build_security_features`): reshapes trade and
  security-master rows into per-security features — trade count, total
  quantity, VWAP, traded price range and total traded notional.
  Securities with no trades keep null price features, not invented ones.
- **Validation** (`validate_novel_dataset`): required columns, unique
  keys, orphan references against the security master, score ranges,
  positive rates, and freshness vs the as-of date.
- **Alerts** (`evaluate_alerts`): automated qualitative data alerts —
  stale rows, columns below 95% complete, row-count drift over 10% vs
  the prior day, VWAP outside 50–150, and a traded price range over 30%
  of VWAP.
- **Investment-team summary** (`investment_team_summary`): datasets
  onboarded, securities with trades, top three by traded notional, and
  open alerts — the preliminary analysis shared with investment teams.

```bash
PYTHONPATH=. python run_onboarding.py
```

## Run the tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## Run the full validation

```bash
PYTHONPATH=. python -m investment_data_validation
```

Prints a per-dataset summary with every finding and writes
`validation_report.json`.

## Demo results (seeded synthetic data, as of 2026-11-20)

- Security master: 40 records, 880 checks, 5 failures — bad CUSIP check digit
  (SEC-9001), duplicate CUSIP (SEC-9002), maturity before issue
  (SEC-9003), negative coupon and zero face value (SEC-9004).
- Trades: 60 records, 960 checks, 7 failures — settlement before trade
  (TRD-9901, fails both the date and the lag check), duplicate trade id
  (TRD-5001), unknown security (TRD-9903), zero quantity and negative
  price (TRD-9904), future-dated trade (TRD-9905).
- Yield curve: 9 points, 47 checks, 2 failures — 7Y tenor missing, 20Y
  point stale (stamped yesterday) — plus a warning for the 10Y yield
  jumping 80bp.
- Warehouse reconciliation: 36 legacy rows vs 36 warehouse rows, 74
  checks, 4 failures — SEC-1005 missing from the warehouse, SEC-8888
  orphaned in it, SEC-1010 market value 10% higher in the warehouse,
  and total market value off by 0.62% (over the 0.01% tolerance).
- Dataset onboarding: ESG scores 36 rows, 184 checks, 0 failures, 2
  warnings — a missing governance score and an environmental score of
  104.5. Corporate actions 14 rows, 32 checks, 2 failures — a duplicate
  action id and an action on an unknown security. FX rates 6 rows, 10
  checks, 0 failures, 2 warnings — a missing spot rate and a stale row.
  Features built for 40 securities (26 with trades); 3 alerts open —
  stale FX rows, spot-rate completeness 83%, and SEC-1017's traded
  price range of 215.6% of VWAP, which traces to the planted bad trade
  priced at −99.5.

## How it differs from the other validation projects in this repo

- `investment-model-governance-validator` validates investment **models**
  (alpha signals, portfolio optimisation, VaR backtests, governance).
  This project validates investment **data** — the security master,
  trades, and yields that feed those models.
- `lakehouse-data-quality` validates a generic retail-orders lakehouse
  (bronze/silver/gold). This project is fixed-income specific: CUSIP and
  ISIN check digits, yield curves, settlement lags, and a legacy-to-
  warehouse reconciliation for an investment data warehouse.
- `cross-asset-model-validation-suite` checks pricing-model invariants.
  This project checks the underlying data before any model runs.
