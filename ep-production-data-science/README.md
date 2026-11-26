# E&P Production Data Science

Data pipelines, decline-curve analysis, and a production-forecasting model
for exploration & production (E&P) well data — the kind of work a Senior
Data Scientist on Halliburton Landmark would do: turn raw well and
production data into models that energy teams can use, validate them, and
package them for deployment.

**All data is synthetic and seeded.** Monthly well production is simulated
from Arps decline curves with lognormal noise; no real well, operator, or
production data is used, and nothing here is a claim about any real well.

## What it does

1. **Generates E&P data** (`ep_data/data.py`): 40 wells across 5 basins
   (Permian, Eagle Ford, Bakken, DJ Basin, Haynesville) with completion
   attributes (lateral length, proppant) and 36 months of oil, gas, and
   water production following Arps hyperbolic decline. A quality-issue
   injector adds the mess real data has: duplicate rows, negative rates,
   missing gas volumes.
2. **Cleans and integrates** (`ep_data/cleaning.py`): drops duplicate
   (well, month) rows and negative-rate rows, interpolates missing gas
   within each well's own history (never across wells), and validates every
   column against the data dictionary — types, ranges, no nulls left.
   Every rule is logged for audit. On the demo dataset: 1,448 raw rows ->
   1,435 clean rows (8 duplicates, 5 negative rows dropped, 6 gas values
   interpolated), 0 nulls remaining, 0 dictionary issues.
3. **Engineers features** (`ep_data/features.py`): cumulative oil/gas/water,
   water cut, gas-oil ratio, 3-month rolling oil average, month-on-month
   decline rate, proppant intensity (lbs per lateral foot). All features use
   only information available up to that month — no look-ahead.
4. **Fits Arps decline curves** (`ep_data/decline.py`): grid search over
   (b, di) with qi by least squares on the log scale, plus EUR (estimated
   ultimate recovery) integrated out to a 5 bbl/day economic limit or a
   30-year horizon. Example well: qi=965 bbl/d, di=0.107, b=1.00,
   R²(log)=0.980, EUR ≈ 1.01 MMbbl (rate still above the economic limit at
   the 30-year horizon).
5. **Forecasts production** (`ep_data/forecast.py`): ridge regression
   (numpy closed form) predicting next-month oil from the feature set.
   Backtest is by time — train on the first 24 months, test on the last
   12 — never a random split. Result: RMSE 876.5 bbl, MAPE 9.3%, beating
   the persistence baseline (RMSE 1,006.9 bbl).
6. **Validates the model** (`ep_data/deployment.py`): backtest vs baseline,
   residual-bias check, per-well decline-fit quality (median R²(log) > 0.80),
   and a data-quality gate. All checks pass on the demo dataset.
7. **Packages for deployment** (`ep_data/deployment.py`): the trained model
   (weights, feature list, standardisation, version 1.0.0) is serialised to
   a JSON artifact a deployment platform can load without the training
   code, with a `load_and_predict` entry point. A loaded artifact predicts
   6,735.7 bbl for one well-month against an actual next-month 6,839.4 bbl.

## Data dictionary

| Column | Meaning |
|---|---|
| api_number | Well identifier, 14-digit API number (synthetic) |
| basin | Sedimentary basin the well is drilled in |
| completion_date | Date the well was completed (first production month) |
| lateral_ft | Horizontal lateral length, feet |
| proppant_lbs | Total proppant pumped during completion, pounds |
| month_index | Months since first production (0-based) |
| oil_bbl | Oil produced in the month, barrels |
| gas_mcf | Gas produced in the month, thousand cubic feet |
| water_bbl | Water produced in the month, barrels |
| days_on | Days the well produced in the month (0–31) |

Derived features: `cum_oil_bbl`, `cum_gas_mcf`, `cum_water_bbl`,
`water_cut`, `gor_mcf_bbl`, `oil_3m_avg`, `decline_rate`,
`proppant_intensity`, `months_on_prod`, `oil_bbl_lag1`.

## How to run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_ep.py
```

## Test results

- **11 pytest tests, all passing** (`tests/test_ep.py`, `tests/test_deployment.py`):
  data generation and decline shape, cleaning (duplicates / negatives /
  nulls), feature ranges and no-look-ahead, Arps fit recovering known
  parameters (R²(log) > 0.99 on synthetic truth), EUR bounds, backtest
  beating the persistence baseline, validation report passing, and a
  packaged-artifact round-trip (load from JSON and predict).

## Honest limits

- All data is synthetic and seeded; this is not production E&P experience,
  and the resume does not claim otherwise.
- Arps decline is a smooth empirical curve: it does not model workovers,
  shut-ins, or choke changes, which move real well rates.
- The forecaster is a linear ridge model on engineered features; real
  production forecasting often needs nonlinear or physics-informed models.
- The deployment artifact is a JSON file, not a deployed service: no
  container, CI/CD pipeline, or model-monitoring loop is included.
