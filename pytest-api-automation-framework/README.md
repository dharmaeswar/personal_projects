# PyTest API Automation Framework

A small, reusable REST API test framework in Python:

- Session-scoped fixture boots the system under test (a stdlib sample API) once per run.
- Tests cover health, list/get endpoints, JSON schema shape, data invariants, and 404 handling.
- Plain `urllib` client keeps dependencies to PyTest only; the client layer can be swapped for `requests` or a service-specific SDK without changing test intent.
- Layout mirrors production SDET practice: SUT in `sample_api/`, tests in `tests/`, shared setup in `conftest.py`.

## Run

```bash
pip install pytest
PYTHONPATH=. pytest -q
```
