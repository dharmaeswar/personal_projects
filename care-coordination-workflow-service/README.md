# Care Coordination Workflow Service

An event-driven care-coordination workflow service built as a portfolio
project for a Senior Software Engineer application at Clover Health /
Counterpart Health. It models the core of a care-coordination platform:
care plans, referrals and tasks as a state-machine-driven service, with a
transactional outbox, idempotent event handling, retries with backoff, and
a full audit trail — plus a small HTTP API and a CLI demo.

**All data is synthetic and de-identified.** Patient references are opaque
`PAT-####` IDs; there are no names, dates of birth, MRNs, or real health
records, no network access, and no real clinical data. Nothing here is a
claim about any real company's systems.

## What it does

- **Care plans, referrals, tasks** (`care_coord/service.py`) — each is a
  state machine with enforced transitions (a plan cannot complete while a
  referral or task is still open; a referral cannot jump from requested to
  scheduled). Every mutation writes an audit entry.
- **Transactional outbox** (`care_coord/events.py`) — every write enqueues
  its domain event in the same step as the mutation, so an event can never
  be lost if the process crashes after the write.
- **Idempotent delivery** — the dispatcher records each event's idempotency
  key after a successful handler run and skips keys already seen, so a
  retry or duplicate delivery is a no-op. Combined with at-least-once
  delivery this gives effectively-once processing.
- **Retries with backoff** — a failing handler is retried up to 3 times
  with exponential backoff (0.1s, 0.2s, 0.4s, capped at 5s), then
  dead-lettered (marked delivered so it stops being retried).
- **Idempotent writes** — API/service calls accept a `request_key`; a
  retried client call returns the original result instead of duplicating
  the record.
- **Audit trail** (`care_coord/store.py`) — append-only, actor + action +
  aggregate + detail, queryable per care plan.
- **HTTP API** (`care_coord/api.py`) — stdlib-only `http.server` API:
  create/list/get care plans, transitions for plans/referrals/tasks,
  audit listing, and an outbox drain endpoint.
- **AI-agent assist** (`care_coord/agent_assist.py`) — a deterministic,
  rule-based suggestion engine that plays the AI agent partner: it reads
  a plan's state and proposes next steps (follow up a referral stalled
  7+ days, escalate a blocked task, complete a plan whose work is all
  done, review an on-hold plan with nothing open). Nothing applies on
  its own: every suggestion stays proposed until a human operator
  approves or rejects it, the decision is written to the audit trail,
  and approval applies the change through the normal service methods
  so state machines, outbox events and idempotency still hold.
  Re-suggesting a plan never duplicates an open suggestion.
- **CLI demo** (`run_demo.py`) — runs three synthetic patients through
  the full workflow and prints the outcome, then demos agent assist on
  a stalled fourth plan (one suggestion approved, one rejected).

## How it differs from the other projects in this repo

- `agentic-clinical-assistant` is an AI agent product (RAG + tool-calling
  over care guidance). This project is the workflow platform underneath
  that kind of product: the durable state machine, outbox and audit
  plumbing a coordination service needs.
- `freight-ops-fullstack` is a freight operations app, not healthcare
  workflow.
- `python-backend-api-service` is a generic API scaffold with no domain
  state machines, outbox, or idempotency semantics.

## Run it

```bash
python3 run_demo.py                 # run the demo workflow, print a summary
python3 run_demo.py --serve         # demo, then serve the API on :8000
python3 -m pytest tests/ -q         # 54 tests
```

Example API flow:

```bash
curl -X POST localhost:8000/care-plans \
  -d '{"patient_ref": "PAT-0001", "title": "Post-discharge follow-up"}'
curl -X POST localhost:8000/care-plans/<id>/transition -d '{"status": "active"}'
curl -X POST localhost:8000/care-plans/<id>/referrals -d '{"specialty": "cardiology"}'
curl -X POST localhost:8000/outbox/process -d '{}'
```

## Layout

```
care_coord/
  models.py    domain models + allowed-transition tables
  store.py     in-memory store: aggregates, outbox, audit, idempotency keys
  events.py    outbox dispatcher: retries, backoff, idempotent delivery
  service.py   workflow service: plans, referrals, tasks, audit, outbox
  api.py       stdlib HTTP API
run_demo.py    CLI demo over synthetic de-identified data
tests/         40 pytest tests (service, events, API)
```

## Tests

40 pytest tests cover: plan/referral/task state machines (valid and
invalid transitions), plan completion blocked by open work, idempotent
writes with the same request key, outbox retries and dead-lettering after
3 attempts, duplicate-delivery skipping, backoff growth, and the full
HTTP workflow including 400/404/409 error paths.
