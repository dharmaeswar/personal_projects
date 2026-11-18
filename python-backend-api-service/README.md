# Python Backend API Service — Installment-Loan Checkout

A Python backend service for pay-over-time checkout, in the domain of a
fintech lender (installment loans at checkout). It exposes a small REST API:
create an installment loan, fetch its amortization schedule, and apply
payments against it.

Built for the Affirm — Software Engineer II, Backend application
(Greenhouse job ID 8196112003).

## What it does

- `POST /v1/checkout` — create a loan from principal, APR, term, merchant
  and customer. Validates every field and returns the loan with its total
  due. Accepts an `Idempotency-Key` header: a retried checkout with the same
  key returns the original loan instead of creating a duplicate.
- `GET /v1/loans/{id}` — loan summary (status, paid amount, total due).
- `GET /v1/loans/{id}/schedule` — the monthly amortization schedule.
- `POST /v1/loans/{id}/payments` — apply a payment; overpayments are
  rejected and the loan flips to `paid_off` when fully paid.
- `GET /health` — liveness check.

Engineering points that match the role:

- **Correct money math** — amounts are integer cents; the schedule always
  closes to exactly zero (the last installment absorbs rounding).
- **Idempotency** — safe client retries, backed by a thread-safe store.
- **Retry with exponential backoff** — the checkout writes through to a
  downstream ledger with bounded retries (3 attempts, 50ms / 100ms delays).
- **Input validation** — principal $1–$100,000, APR 0–36%, term 3–60 months,
  strict id formats; bad input returns 400 with a clear error.
- **Structured logging** — one JSON log line per request (method, path,
  status, latency).
- **Threaded HTTP server** — `ThreadingHTTPServer`, thread-safe stores.

## What runs where / what is simulated

- **Real:** the HTTP API, the amortization math, validation, idempotency,
  retry logic, logging — all run locally with the Python 3.11+ standard
  library only. No third-party packages are needed to run the service.
- **Simulated:** the downstream ledger is a `SimulatedLedger` class that
  records the loan in memory and can be told to fail transiently so the
  retry path is exercised. Loans live in an in-memory store (no database);
  restarting the service clears them. There is no real money, no real
  merchant, and no AWS / MySQL / Kubernetes deployment here — the service
  is written so those could be added behind the store and ledger interfaces.

## Run it

```bash
python run_service.py        # listens on http://127.0.0.1:8000
```

```bash
curl -X POST http://127.0.0.1:8000/v1/checkout \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' \
  -d '{"principal_cents": 120000, "apr_bps": 1500, "term_months": 12,
       "merchant_id": "merchant_1", "customer_id": "cust_42"}'
# -> {"id": "loan_000001", ..., "total_due_cents": 129972, "status": "active"}

curl http://127.0.0.1:8000/v1/loans/loan_000001/schedule
```

## Verified results (Nov 18, 2026, Python 3.12, pytest)

```
31 passed in 0.62s
```

- 24 unit tests: installment math, validation, payments, idempotency, retry.
- 7 integration tests: live HTTP server on a real socket (health, checkout,
  validation 400, idempotent re-checkout creating no duplicate loan,
  payment flow to `paid_off`, 404s).

Worked example, verified by a live run: a $1,200 loan at 15% APR over
12 months costs 12 × $108.31 = $1,299.72 total ($1,200 principal +
$99.72 interest). First installment: $93.31 principal + $15.00 interest;
last installment closes the balance to exactly $0.

## Layout

```
payments_api/
  app.py          HTTP layer, routing, structured logging
  models.py       validation, amortization schedule, Loan
  idempotency.py  idempotency store, retry w/ backoff, simulated ledger
run_service.py    entry point
tests/
  test_service.py unit tests
  test_api.py     integration tests against a live server
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```
