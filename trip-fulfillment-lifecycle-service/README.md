# Trip Fulfillment Lifecycle Service

A backend platform service modelling the trip fulfillment flow Uber's
Fulfillment Platform describes: shopping, ordering, matching & dispatching,
and tracking phases for orders and trips, with pricing, matching and
dynamics integrated into the lifecycle. Built as the role project for
**Uber — Software Engineer II, Backend (Fulfillment Platform), Job 304922**.

**All data is synthetic and seeded.** Nothing here describes a real Uber
system, real trips, real drivers, or real fares. The service runs locally
with the Python standard library only — no Kafka, no database, no cloud.

## Problem statement

A fulfillment platform must own a trip end to end across business
verticals (rides, delivery, groceries, package): quote the fare, create
the trip, match a driver, dispatch, track pickup and progress, and close
the trip out — in real time, at high scale, without ever letting a trip
skip a phase, move after it is terminal, or get created twice by a retry.

## What it does

| Module | Fulfillment Platform duty it maps to |
|---|---|
| `fulfillment/lifecycle.py` | **Trip lifecycle** — ordered state machine (requested → searching → matched → dispatched → pickup → in_progress → completed/cancelled); illegal jumps rejected |
| `fulfillment/pricing.py` | **Pricing integration** — fare quote (base + distance + time) with a dynamics/surge multiplier and a minimum fare; quotes expire after 5 minutes and are frozen onto the trip |
| `fulfillment/matching.py` | **Matching** — deterministic driver scoring (ETA dominates, rating bonus, consecutive-trip spread); only online drivers in radius with enough seats are eligible |
| `fulfillment/events.py` | **Tracking** — append-only per-trip event log with monotonic sequence numbers, resume-from-offset reads, and idempotent event ids for at-least-once delivery |
| `fulfillment/service.py` | **Orchestration** — `FulfillmentService` owns request → match/dispatch → advance → complete/cancel, idempotency keys on trip creation, and a per-vertical reliability report |
| `fulfillment/api.py` | **Platform API** — stdlib HTTP API (`/quote`, `/trips`, `/trips/{id}/match|advance|cancel`, `/trips/{id}/events`, `/report`) |

## Run it

```bash
python3 -m pytest -q          # tests
python3 run_service.py        # demo: quote -> match -> dispatch -> complete
python3 -m fulfillment.api    # HTTP API on http://127.0.0.1:8080
```

Demo output (seeded drivers around downtown San Francisco):

```
Quote: $22.75 (base 250 + distance 1020 + time 550) x 1.25 surge
Matched driver drv-001 (rating 4.9)
Trip trip-000001: requested -> searching -> matched -> dispatched -> pickup -> in_progress -> completed
Events: 7
Reliability report: {'rider': {'completed': 1, 'cancelled': 0, 'active': 0}}
```

## Tests

28 tests, all passing (`python3 -m pytest -q`):

- Lifecycle: full happy path, illegal jumps rejected, cancel from any live state, terminal states accept no transitions.
- Pricing: base/distance/time math, surge multiplication, minimum-fare floor, 5-minute quote expiry, negative inputs rejected.
- Matching: haversine distance, closest driver wins, offline drivers never matched, empty radius returns none, seat requirement filters, rating breaks ties.
- Service: end-to-end trip, idempotent retry returns the same trip, expired quote rejected, no-driver cancels the trip, terminal trips cannot advance, unknown trip raises, reliability report counts by vertical, event-log dedupe and resume.
- API: quote endpoint, full trip flow over HTTP, unknown trip returns 404.

## Honest limits

All fares, drivers, and locations are synthetic examples; nothing describes
a real Uber system, real fares, or real trip data. The store is in-memory,
not a database; the "API" runs on a stdlib HTTP server, not on a production
stack. The matching score is a deterministic heuristic, not a production
matching model, and it runs on five seeded drivers, not at production scale.
Not implemented: real distributed deployment, high-availability/multi-region
operation, real payments integration, auth/rate-limiting, persistence.
