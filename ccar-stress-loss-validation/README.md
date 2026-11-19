# CCAR Stress-Loss Validation

A portfolio project for a Quantitative Model Validation role. It validates a
loan-portfolio stress-loss forecasting model the way a model-validation team
would: outcomes analysis, calibration, CCAR-style scenario analysis, and
ongoing monitoring.

**All data is synthetic and seeded.** No real borrower, bank, or regulatory
data is used, and nothing here is a claim about any real institution.

## What it validates

- **Champion model**: logistic-regression default forecaster, mapped to a
  loss-rate forecast via loss severity.
- **Challenger model**: linear regression directly on the observed loss rate.
- **Benchmark model**: historical average loss rate (no features).
- **Agency prepayment model validation** (new, Nov 2026): CPR/PSA prepayment
  speeds for a synthetic agency mortgage pool, rate-incentive sensitivity
  scenarios (+/-200bps), seasoning and burnout behaviour, monotonicity
  checks, and calibration by rate-incentive bucket.
- **Outcomes analysis**: bias, MAE, RMSE, hit rate within a tolerance band,
  and calibration by predicted decile.
- **Scenario analysis**: baseline vs severely adverse CCAR-style macro paths
  over 9 quarters; stressed forecasts should rise under the adverse path.
- **Ongoing monitoring**: mean drift in basis points and Population Stability
  Index (PSI) per feature.

## How to run

```bash
pip install -r requirements.txt
python run_validation.py
```

This prints the validation report and writes it to `validation_report.txt`.

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```

## Layout

- `ccar_validation/data.py` — seeded synthetic loan-portfolio generator
- `ccar_validation/prepayment.py` — agency prepayment model: CPR/PSA speeds,
  rate-incentive sensitivity, seasoning/burnout, calibration by incentive
- `ccar_validation/models.py` — champion / challenger / benchmark models
- `ccar_validation/backtest.py` — outcomes analysis metrics
- `ccar_validation/scenarios.py` — CCAR-style scenario paths and forecasts
- `ccar_validation/monitoring.py` — drift (bps) and PSI
- `ccar_validation/report.py` — plain-text validation report writer
- `run_validation.py` — CLI entry point
- `tests/` — pytest test suite
