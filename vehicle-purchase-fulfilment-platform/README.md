# Vehicle Purchase Fulfilment Platform

A working model of the backend behind an online used-vehicle purchase:
a customer reserves a car, it passes inspection and reconditioning,
financing is approved, delivery is scheduled, and the car is delivered
to the driveway. Every step is an event on a Kafka-style log, orders
live in SQL, vehicle listings live in a NoSQL document store, and the
service ships with Kubernetes manifests and a web dashboard.

Built as the role project for the **Carvana — Senior Software Engineer**
(Greenhouse gh_jid 6212836, Tempe AZ) role, whose stack is C#/.NET or
JavaScript/TypeScript React, GraphQL and REST APIs, Kafka, SQL/NoSQL,
and Kubernetes. This project is written in Python (standard library
only, plus pytest) and models each of those pieces in working code:
a REST API plus a GraphQL-style query endpoint, a partitioned event
log with consumer groups and a dead-letter queue, SQLite persistence
plus a JSON document store, and Kubernetes Deployment / Service /
HPA manifests.

**All data is synthetic.** No real Carvana vehicle, customer, order or
payment data is used, and nothing here describes a real Carvana system
or a production platform. The C#/.NET and React/TypeScript parts of the
posting are not claimed: this project demonstrates the backend,
streaming, persistence and deployment side in Python, and its README
says so plainly.

## What it does

- **Order lifecycle** (`vehicle_platform/orders.py`) — a strict state
  machine: `RESERVED → INSPECTED → FINANCED → DELIVERY_SCHEDULED →
  DELIVERED`, with `CANCELLED` reachable from any pre-delivery state.
  Illegal transitions are rejected with a plain reason. Pricing is
  computed with `decimal`: list price + $599 documentation fee +
  delivery fee + state sales tax, all in integer cents.
- **Event log** (`vehicle_platform/events.py`) — a Kafka-style
  append-only log: topics partitioned by key hash, per-partition
  offsets, consumer groups with committed offsets, and a dead-letter
  queue for events that fail validation. Every order transition
  publishes one event; replays rebuild order state from the log.
- **Persistence** (`vehicle_platform/store.py`) — orders and payments
  in SQLite (relational, with indexes on order id and customer id);
  vehicle listings in a JSON document store (NoSQL-style: VIN-keyed
  documents holding make, model, year, mileage, 360° photo set and
  feature list). One write path updates both stores and the log.
- **API** (`vehicle_platform/api.py`) — a REST API over
  `http.server`: `POST /v1/orders`, `GET /v1/orders/{id}`,
  `POST /v1/orders/{id}/advance`, `GET /v1/vehicles/{vin}`,
  `POST /v1/graphql` (a small GraphQL-style query endpoint for
  vehicles and orders), `GET /health`, and a `GET /` dashboard page.
  Every write is validated, idempotent on `Idempotency-Key`, and
  returns one error shape.
- **Kubernetes** (`vehicle_platform/k8s/`) — Deployment (3 replicas,
  CPU/memory requests and limits, liveness and readiness probes),
  Service, and a HorizontalPodAutoscaler (2–10 replicas at 70% CPU).

## Skills used

Only skills Dharma has verified: Python, SQL, Bash, Linux, PyTest,
Git, Jenkins, Kubernetes, Terraform, EKS. Kafka event pipelines were
built at AMDOCS (Spring Boot + Kafka streaming usage events between
billing and rating systems); the event log here is a local model of
that pattern, not a claim of production Kafka operation. This project
does **not** claim C#/.NET, TypeScript, React, GraphQL production
experience, CosmosDB, Azure Functions, or production Kubernetes
operation — the GraphQL endpoint is a small query layer, the NoSQL
store is a JSON document store, and the Kubernetes manifests are
declarative YAML checked by tests.

## Run it

```bash
python3 -m pytest -q            # 38 tests
python3 run_demo.py             # seeds 3 vehicles, runs one order end to end
python3 -m vehicle_platform.api # serves the API on http://localhost:8080
```

## Demo flow

`run_demo.py` reserves a 2021 Honda Civic, advances it through
inspection, financing and delivery scheduling, prints the order total
($24,500 list + $599 doc fee + $199 delivery + 8.1% AZ tax), then
replays the event log to prove the rebuilt order matches the stored
one.
