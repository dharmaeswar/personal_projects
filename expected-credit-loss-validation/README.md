# Expected Credit Loss Validation

IFRS 9 / CECL expected credit loss (ECL) validation toolkit in pure Python
(standard library only, plus pytest for tests). Built for the Barclays
Quantitative Analyst — Risk Modeler role: it covers the full workflow in
that job description — staging, ECL calculation, back-testing,
benchmarking, monitoring and SR 11-7-style documentation.

## What it does

- **IFRS 9 staging** — Stage 1 / 2 / 3 with significant-increase-in-credit-risk
  (SICR) triggers: 30+ days past due, or a credit-score drop of 100+ points.
  Stage 3 is default or 90+ days past due.
- **ECL math** — 12-month ECL (PD x LGD x EAD) for Stage 1, lifetime ECL for
  Stages 2 and 3 (Stage 3 uses PD = 1.0). CECL lifetime ECL for every loan.
- **Back-testing** — predicted IFRS 9 ECL vs realised losses: coverage ratio,
  mean absolute error, under-predicted loan count, breach flag when coverage
  sits outside [0.80, 1.25].
- **Benchmarking** — primary loan-level PD model vs a score-band challenger
  model, scored on the same realised losses by MAE.
- **Monitoring** — stage mix, coverage, top-10 ECL concentration, with breach
  flags (Stage 2 share > 20%, Stage 3 share > 5%, coverage breach,
  top-10 ECL share > 50%).

## Files

- `ecl_model.py` — staging, ECL, back-test, benchmark, monitoring.
- `portfolio.py` — deterministic synthetic loan portfolio (seeded) and
  realised-loss simulation.
- `run_validation.py` — entry script; prints and writes `validation_report.txt`.
- `tests/test_ecl.py` — 36 pytest tests.

## Run

```bash
python3 run_validation.py
python3 -m pytest tests/ -q
```

## Example output (500-loan portfolio, seed 42)

- Stage counts: Stage 1 = 387, Stage 2 = 84, Stage 3 = 29
- IFRS 9 total ECL: $3,457,899.99; CECL total ECL: $4,349,308.05
- Back-test coverage ratio: 0.80; MAE per loan: $10,409.85
- Benchmark winner: challenger (MAE $9,593.14 vs primary $10,409.85) — the
  report names the gap honestly instead of hiding it.
- Monitoring flags: Stage 3 share 5.8% above the 5% limit; coverage at the
  lower bound.

## Honest scope

The portfolio and realised losses are synthetic and seeded for
reproducibility — this is a validation-methods demo, not production credit
data. No IFRS 9 / CECL production experience is claimed: the toolkit shows
the methods (staging rules, ECL arithmetic, back-test and benchmark design)
applied end to end with tests.
