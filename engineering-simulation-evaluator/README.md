# Engineering Simulation Evaluator

Evaluation harness for engineering and applied-science design tasks: the kind
of rigorous measurement an Applied Scientist builds to judge whether an AI
system can invent, design and engineer reliably — analytic simulators as
ground truth, calibration of those simulators against measurements, and
scoring of candidate designs against requirements.

## What it does

- **Beam simulator** (`eng_sim_evaluator/beam.py`): Euler-Bernoulli cantilever
  beam — deflection profile, tip deflection, max bending stress, first natural
  frequency, mass. Analytic formulas, so the simulator itself is exact.
- **Thermal simulator** (`eng_sim_evaluator/thermal.py`): steady-state 1D heat
  conduction through single and composite walls (Fourier's law).
- **Calibration** (`eng_sim_evaluator/calibration.py`): recovers Young's
  modulus from noisy deflection measurements by grid search, the way a
  simulator is calibrated against real-world lab data before it is trusted.
- **Benchmark** (`eng_sim_evaluator/benchmark.py`): scores candidate designs
  against deflection / stress / mass requirements, ranks them by safety
  margin, and compares an AI-proposed design set with a reference solver's
  outputs (MAE, max error, share within tolerance).
- **Metrics** (`eng_sim_evaluator/metrics.py`): MAE, RMSE, max absolute error,
  within-tolerance share.

## Run

```bash
pip install -r requirements.txt
python run_evaluation.py
python -m pytest -q
```

## Results (seeded, reproducible)

- Beam benchmark: 3 candidate designs scored; the 100 mm steel section ranks
  first (largest safety margins); all 3 are feasible at a 1,000 N tip load.
- Calibration: Young's modulus recovered exactly from synthetic measurements
  (200 GPa true, 200 GPa recovered, 0.00% error) at 1e-6 m noise.
- Thermal: composite wall (0.1 m insulation + 0.1 m concrete, 100 to 20 C)
  passes 266.7 W/m^2.
- Solver comparison: 4 AI-proposed designs vs reference — MAE 0.00006 m,
  max error 0.00010 m, 100% within a 0.0002 m tolerance.

## Honesty note

All measurements are **synthetic** (seeded random noise around the analytic
model) — this is a demonstration harness, not production engineering data and
not a claim of work with manufacturers or labs. The physics formulas are
standard textbook results (Euler-Bernoulli beam theory, Fourier conduction).

## Author

Built as a role-matching project for an Applied Scientist (engineering /
applied science evaluation) application. Solo work, Python standard library
only, pytest for tests.
