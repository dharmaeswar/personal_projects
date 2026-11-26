# PyTest API Automation Framework

A small, reusable REST API test framework in Python:

- Session-scoped fixture boots the system under test (a stdlib sample API) once per run.
- Tests cover health, list/get endpoints, JSON schema shape, data invariants, and 404 handling.
- High-volume data tests (`tests/test_volume_api.py`): the sample API serves 5,000 deterministic trade
  records through a paged `/trades` endpoint; tests page the whole dataset with no overlap or loss,
  check per-record invariants (positive price, quantity bounds, valid side/symbol, increasing timestamps),
  reject bad paging with 400, and hold a 1,000-row page inside a 2-second latency budget.
- Contract / schema checks (`qaops/contracts.py`, `tests/test_contracts.py`): a stdlib-only JSON
  contract validator (types, required keys, ranges, enums, regex, nested objects and arrays) applied
  to live plan and trade payloads, so a schema break fails as a readable violation list, not an error.
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

- `qaops/contracts.py` — JSON contract validation for API responses: declare the expected shape
  (types, required keys, numeric ranges, enums, patterns, nested objects/arrays) and get back a list
  of violations; empty means the payload satisfies the contract.
- `sample_api/server.py` — also serves `/trades`: 5,000 deterministic trade records, paged with
  `?limit=&offset=`, plus `/trades/<id>`.

```bash
PYTHONPATH=. pytest -q          # 34 tests: API suite + volume + contract + qaops unit tests
python3 run_gate.py             # health checks + suite + JSON gate report, exit 0 on PASS
```

## Run

```bash
pip install pytest
PYTHONPATH=. pytest -q
```
