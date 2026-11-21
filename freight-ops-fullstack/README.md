# Freight Ops — Full-Stack Rail Shipment Tracking

A full-stack demo app for tracking rail freight shipments: a Python REST
API plus a browser shipment board (plain HTML/CSS/JavaScript) that calls
that API, with a dashboard summary and Prometheus-format metrics.

Built for the BNSF Railway — Product, Platform & Enterprise Full Stack
Software Engineer I/II (Remote US) application.

**Demo project. Synthetic data only. Not a real railroad system.** Nothing
here contacts a real carrier, and no production deployment, customer use,
or real shipment history is claimed.

## What it does

Backend (Python standard library only, no web framework):

- `GET /` — the shipment board UI: a status-filtered table of shipments,
  a create-shipment form, and a detail view with events and ETA. The page
  fetches data from the API with `fetch()`; no front-end framework.
- `POST /v1/shipments` — create a shipment (reference, origin,
  destination, car count, weight, distance). Every field is validated;
  bad input returns 400 with an error message.
- `GET /v1/shipments?status=` — list shipments, optionally filtered by
  status (`booked`, `in_transit`, `delayed`, `delivered`).
- `GET /v1/shipments/{id}` — one shipment with its tracking-event timeline.
- `POST /v1/shipments/{id}/events` — append a tracking event (`departed`,
  `arrived_yard`, `delayed`, `delivered`); the shipment status follows the
  latest event, and delivery zeroes the remaining distance.
- `POST /v1/shipments/{id}/progress` — update distance remaining along the
  route (bounded by the shipment's total distance).
- `GET /v1/shipments/{id}/eta` — ETA estimate: distance remaining divided
  by a 28 mph planning speed, with a 25% buffer while a shipment is
  delayed. Both numbers are planning assumptions stated here, not measured
  averages.
- `GET /v1/dashboard` — counts by status, total cars, deliveries, and an
  on-time rate (delivered shipments with no `delayed` event).
- `GET /health` — liveness check. `GET /metrics` — Prometheus text format:
  request counts by method/path/status and shipments by status.

## Skills used

Only skills Dharma has verified: Python, JavaScript, HTML, CSS, REST APIs,
JSON, pytest, Linux. This project does **not** claim React, Angular,
Node.js, Spring Boot, Go, or a production Prometheus/Grafana/OpenTelemetry
deployment — the metrics endpoint only emits Prometheus-format text, and
the ETA math is a stated planning assumption.

## Run it

```bash
python run_service.py        # listens on http://127.0.0.1:8000
python run_service.py 9000   # custom port
```

Open http://127.0.0.1:8000 in a browser: create a shipment on the form,
click its row to see events and ETA.

## Tests

```bash
python -m pytest -q
```

22 tests: store validation and event flow, ETA math, and end-to-end HTTP
tests (API + UI + metrics) against a live local server.

## Live demo (local run)

1. Create a shipment: Fort Worth, TX → Chicago, IL, 40 cars, 925 miles.
2. Post a `departed` event from Fort Worth — status becomes `in_transit`.
3. Post progress of 560 miles remaining — ETA reads 20.0 hours (560 / 28).
4. Post a `delayed` event — status becomes `delayed` and the ETA gains the
   25% buffer (25.0 hours). Post `delivered` and the shipment closes with
   0 miles remaining.
