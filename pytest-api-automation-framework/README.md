# PyTest API Automation Framework

A small, reusable REST API test framework in Python:

- Session-scoped fixture boots the system under test (a stdlib sample API) once per run.
- Tests cover health, list/get endpoints, JSON schema shape, data invariants, and 404 handling.
- Plain `urllib` client keeps dependencies to PyTest only; the client layer can be swapped for `requests` or a service-specific SDK without changing test intent.
- Layout mirrors production SDET practice: SUT in `sample_api/`, tests in `tests/`, shared setup in `conftest.py`.

## QA/DevOps release gate (`qaops/` + `run_gate.py`)

The framework also ships the release-gate tooling a QA/DevOps engineer runs before a business-systems
release is promoted:

- `qaops/health.py` — environment health checks: probe HTTP endpoints for expected status, latency
  budget and required JSON keys, plus a required-config check. Each check returns a structured result.
- `qaops/gate.py` — release-gate decision from a pytest summary: no failures or errors, pass rate at
  or above the minimum (default 1.0), and every required check passed. Report is JSON for CI.
- `run_gate.py` — runs the health checks, then the suite, then prints the gate report. Exit 0 on PASS.

```bash
PYTHONPATH=. pytest -q          # 19 tests: API suite + qaops unit tests
python3 run_gate.py             # health checks + suite + JSON gate report, exit 0 on PASS
```

## Run

```bash
pip install pytest
PYTHONPATH=. pytest -q
```
