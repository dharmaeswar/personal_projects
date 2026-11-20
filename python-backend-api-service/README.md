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

It also has a Communications Platform module (`payments_api/comms.py`)
for transactional messaging about the loan product:

- `POST /v1/comms/messages` — render a template (`payment_due`,
  `payment_received`, `loan_approved`) and deliver it to the user's
  enabled channels (email, SMS, push, Slack, Teams, WhatsApp). Accepts an
  `Idempotency-Key` header: a retried send returns the original message
  instead of delivering twice.
- `GET /v1/comms/messages/{id}` — message record with per-channel
  delivery status and provider confirmation ids.
- `GET /v1/comms/delivery` — delivery monitoring: attempts, delivered,
  failed, delivery rate, per channel.
- `GET` / `POST /v1/comms/preferences/{user_id}` — per-user enabled
  channels and digest opt-in; sends only go to enabled channels.
- `POST /v1/comms/digest` — group several messages into one digest per
  user and channel instead of one notification each.

Comms engineering points that match the role:

- **Templating** — `{{placeholder}}` templates; a missing variable fails
  the send instead of delivering a broken message.
- **Provider abstraction** — a `DeliveryProvider` interface; the simulated
  provider stands in for real providers (email / SMS / push / Slack /
  Teams / WhatsApp) and can fail transiently to exercise retries. No real
  provider is called.
- **Idempotent delivery** — safe client retries, backed by the same
  idempotency store as checkout.
- **Safe retries with confirmed delivery** — each channel delivery is
  retried with exponential backoff (bounded attempts) and only marked
  delivered on provider confirmation; exhausted retries are recorded as
  failed, never lost silently.
- **User preferences** — sends respect per-user channel opt-ins.
- **Delivery monitoring** — every attempt is logged; the summary endpoint
  reports counts and delivery rate per channel.

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

It also has an Insurance Policy & Claims module
(`payments_api/insurance.py`), added for the Mercury Insurance —
Software Engineer II (Java) application. No Java toolchain was available
in the build environment, so the insurance domain is implemented in this
same Python service instead of as a separate Java/Spring Boot service; the
patterns are the ones the Java role asks for (REST resources, validation,
integer-cents money math, event publishing, caching, thread-safe stores).

- `POST /v1/policies` — create an auto or home policy from coverage
  limit, deductible, term (6 or 12 months), state and holder. The premium
  is computed in integer cents from the coverage limit, a per-type base
  rate, a deductible credit, a state factor and the term. Publishing a
  `policy.created` event and warming the premium-quote cache.
- `GET /v1/policies/{id}` — policy summary (coverage, deductible, premium).
- `GET /v1/policies/{id}/quote` — premium quote, served from the TTL
  cache when warm (`"cached": true`).
- `POST /v1/policies/{id}/claims` — file a claim; the amount must be
  positive and within the coverage limit. Publishes `claim.filed`.
- `GET /v1/policies/{id}/claims` — claims filed on a policy.
- `POST /v1/claims/{id}/settle` — `{"decision": "approve" | "deny"}`.
  An approved claim settles with payout = amount − deductible (floored
  at zero) and publishes `claim.settled`; a denied claim pays zero.
- `GET /v1/events` — published domain events, optionally filtered with
  `?topic=claim.settled`.

Insurance engineering points that match the role:

- **REST resources with validation** — policies and claims are separate
  resources with strict field validation; bad input returns 400, unknown
  ids return 404, and a claim above the coverage limit is rejected.
- **Event publishing** — `EventPublisher` records domain events with
  Kafka-style topics, keys and per-topic offsets (`policy.created`,
  `claim.filed`, `claim.settled`). It is an in-memory stand-in, not a
  Kafka broker; a real producer would publish the same records to Kafka.
- **Caching** — `QuoteCache` is a TTL cache for premium quotes with the
  same get/set shape as a Redis cache; a real deployment would back it
  with Redis.
- **Correct money math** — premiums and payouts are integer cents;
  payouts never exceed the coverage limit and never go below zero.
- **Thread-safe stores** — policies, claims, events and quotes are held
  behind locks, like the loan store.

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

## Verified results — Communications Platform extension (Nov 20, 2026)

```
51 passed in 2.01s
```

- 20 new comms tests: template rendering and missing-variable errors,
  preference filtering and opt-in, idempotent send delivering once,
  transient provider failure retried then confirmed (2 failures + 1
  success), persistent failure recorded as failed, multi-channel partial
  delivery, delivery monitoring counts and rate, digest grouping, and a
  live-server HTTP flow (send, idempotent re-send, fetch, monitoring,
  preferences, digest, 400 on a missing variable, 404 on an unknown id).
- The 31 earlier tests still pass unchanged.

Worked example, verified by a live run: `POST /v1/comms/messages` with
template `payment_due` for `cust_42` returns `msg_000001`, status
`delivered`, provider id `email_msg_000001`; `GET /v1/comms/delivery`
then reports 1 attempt, 1 delivered, delivery rate 1.0.

Worked example, verified by a live run: a $1,200 loan at 15% APR over
12 months costs 12 × $108.31 = $1,299.72 total ($1,200 principal +
$99.72 interest). First installment: $93.31 principal + $15.00 interest;
last installment closes the balance to exactly $0.

## Verified results — Insurance Policy & Claims extension (Nov 20, 2026)

```
68 passed in 2.69s
```

- 17 new insurance tests: premium math (auto/home rates, deductible
  credit cap and rate floor, 6- vs 12-month terms, state factors),
  validation rejections, claim payout = amount − deductible, claim above
  the coverage limit rejected, deny and double-settle rejected, quote
  cache TTL expiry, event offsets and topic counts, and a live-server HTTP
  flow (create policy, fetch it, cached quote, file a claim, list claims,
  settle with payout, event feed, 400 on bad input, 404 on unknown ids).
- The 51 earlier tests still pass unchanged.

Worked example, verified by a live run: `POST /v1/policies` for an auto
policy ($25,000 coverage, $500 deductible, 12 months, NY) returns
`pol_000001` with premium $825.00; `GET /v1/policies/pol_000001/quote`
returns the same premium with `"cached": true`; a $2,000 claim settles
with payout $1,500 ($2,000 − $500 deductible) and a `claim.settled`
event appears on `GET /v1/events?topic=claim.settled`.

## Layout

```
payments_api/
  app.py          HTTP layer, routing, structured logging
  models.py       validation, amortization schedule, Loan
  idempotency.py  idempotency store, retry w/ backoff, simulated ledger
  comms.py        templates, providers, preferences, delivery, digesting
  insurance.py    policies, premium math, claims, events, quote cache
run_service.py    entry point
tests/
  test_service.py unit tests
  test_api.py     integration tests against a live server
  test_comms.py   comms unit + integration tests
  test_insurance.py insurance unit + integration tests
```

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```
