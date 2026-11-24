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
- **Counterparty credit-risk exposure validation** (new, Nov 2026): Monte
  Carlo mark-to-market simulation for a synthetic book of 25 counterparties
  and 200 interest-rate swaps; Expected Exposure (EE) and PFE95 profiles,
  Effective EPE, EAD (alpha x Effective EPE), expected loss (EAD x PD x
  LGD), netting benefit (gross vs netted exposure), stressed EAD under a
  +200bp parallel rate shock, and a backtest of forecast EE against
  fresh-seed realised exposures with a PFE95 breach-rate check.
- **Macro-forecasting model validation** (new, Nov 2026): unemployment
  sensitivity (losses must rise with unemployment), forecast accuracy by
  expansion/recession regime, coefficient stability across origination
  vintages, and scenario reasonableness (severely adverse beats baseline
  every quarter).
- **Model deployment pipeline** (new, Nov 2026): staged execution pipeline
  (ingest -> score -> validate -> publish) for the champion loss forecaster,
  with score-range and batch-MAE validation gates so a broken model version
  can never publish; a versioned model registry with champion / challenger
  promotion gates (MAE gain vs hit-rate loss); and per-stage timings.
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
- `ccar_validation/macro.py` — macro-forecasting validation: unemployment
  sensitivity, regime accuracy, coefficient stability, scenario reasonableness
- `ccar_validation/prepayment.py` — agency prepayment model: CPR/PSA speeds,
  rate-incentive sensitivity, seasoning/burnout, calibration by incentive
- `ccar_validation/counterparty.py` — counterparty exposure validation:
  synthetic counterparty book, Monte Carlo MtM simulation, EE/PFE profiles,
  EAD, expected loss, netting benefit, stressed EAD, exposure backtest
- `ccar_validation/deployment.py` — model deployment pipeline: staged
  execution (ingest/score/validate/publish), validation gates, versioned
  model registry, champion/challenger promotion gate
- `ccar_validation/models.py` — champion / challenger / benchmark models
- `ccar_validation/backtest.py` — outcomes analysis metrics
- `ccar_validation/scenarios.py` — CCAR-style scenario paths and forecasts
- `ccar_validation/monitoring.py` — drift (bps) and PSI
- `ccar_validation/report.py` — plain-text validation report writer
- `run_validation.py` — CLI entry point
- `tests/` — pytest test suite
