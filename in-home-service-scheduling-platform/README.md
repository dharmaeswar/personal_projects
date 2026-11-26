# In-Home Service Scheduling Platform

An event-sourced, CQRS scheduling service for in-home delivery,
installation, and repair appointments — the shape of Best Buy's
In-Home Order Fulfillment (IHOF) problem: appointments are booked
across selling channels, technicians are assigned, and partner
networks confirm the work.

Built as the role project for the Best Buy Senior Engineer, In-Home
Services application (Req 1040721BR). **All data is synthetic and
local.** No real Best Buy systems, customers, or appointments are
involved, and nothing here describes a real Best Buy platform.

## Problem statement

In-home appointments arrive from every selling channel. The same
technician must never be double-booked, a retried request must never
create a second appointment, and partner dispatch calls can fail
transiently or go down entirely. The service therefore stores every
change as an event, derives all state by replaying events, and
isolates partner failures behind retries and a circuit breaker.

## What it does

- **Event store** (`scheduling/events.py`) — append-only log, one JSON
  object per line, persisted to disk. Appends check the aggregate
  version, so two writers cannot both claim the same version.
- **Commands** (`scheduling/commands.py`) — the write side: schedule,
  reschedule, assign technician, cancel, complete. Each command
  validates against state rebuilt from the aggregate's events, then
  appends exactly one event. Commands carry an idempotency key, so a
  retried request returns the original event instead of double-booking.
  Overlapping bookings for the same technician are rejected.
- **CQRS read models** (`scheduling/projections.py`) — a technician
  day-schedule view and a customer appointment view, built only by
  replaying the event stream. Either view can be rebuilt from scratch
  at any time; there is no separate write path for read data.
- **Resilience** (`scheduling/resilience.py`) — retry with exponential
  backoff and a circuit breaker (closed / open / half-open) that fails
  fast once a partner is persistently down.
- **Partner dispatch** (`scheduling/dispatch.py`) — confirms an
  appointment with a partner network through the retry + breaker path,
  and records each dispatch attempt as an audit event in the store.
- **HTTP API** (`scheduling/api.py`) — standard-library only:
  `POST /v1/appointments` (Idempotency-Key header), reschedule /
  assign / cancel / complete, `GET /v1/technicians/{id}/schedule`,
  `GET /v1/customers/{id}/appointments`, `GET /health`.

## Runs locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python run_demo.py
python3 -m scheduling.api   # serves on :8080
```

Demo run: one installation booked 09:00–11:00, partner dispatch
confirmed after 2 attempts (first attempt times out), rescheduled
to 13:00, completed — 4 events in the store, both read models rebuilt
by replay.

## Test results

- **16 passed, 0 failed** (pytest).
- Covered: event-sourced replay rebuilds state, double-booking
  rejected, idempotent replay writes no duplicate event, full
  lifecycle (schedule → reschedule → complete), reschedule into a
  booked slot rejected, cancelling frees the slot, version conflicts
  detected, projections rebuilt from events, retry after transient
  failures, breaker opens after the failure threshold and recovers
  after cooldown, dispatch retries then succeeds, dispatch fails fast
  when the breaker is open, and the HTTP API end to end.

## Honest limits

Single machine, in-memory projections, JSON-lines file store — not a
distributed system: no multi-node replication, no real Kafka/Spring
runtime (the service is Python, mirroring the CQRS/event-sourced
design rather than the JD's Java Spring stack), no real partner
network (the dispatch transport is injected), no authentication on
the demo API, and no persistence of the read models beyond replay.
The retry path sleeps nothing in the request path by design; backoff
delays are exercised in the unit tests with an injectable sleep.
