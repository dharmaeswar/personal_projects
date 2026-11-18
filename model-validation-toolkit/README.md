# Model Validation Toolkit

Small Python toolkit for independent model validation work:

- **Outcomes analysis** (`outcomes.py`) — back-test summary: bias, MAE, RMSE, hit rate within a 5% band.
- **Sensitivity analysis** (`sensitivity.py`) — bump-and-revalue table for a pricing or scoring function.
- **Drift checks** (`drift.py`) — mean drift in basis points and Population Stability Index (PSI).

## Run the tests

```bash
pip install pytest
PYTHONPATH=. pytest -q
```

Built to match model risk management practice: independent challenge, outcomes
analysis, sensitivity testing, and documented, reproducible checks.
