# Inventory Orchestration Service

A full-stack, event-driven inventory orchestration service for a
multi-warehouse retailer: a REST API plus a browser dashboard, with every
stock movement published as a schema-validated event — the shape of the
microservice a team would run behind an Inventory Orchestration domain.

Built for the Citi — Full Stack Developer (AVP), Inventory Orchestration
application (Req 261011970, Irving, TX): microservices, REST APIs,
event-driven messaging, containerisation and CI/CD.

**Demo project. Synthetic data only.** No real retailer, warehouse, order
history, or customer is involved, and nothing here is a production
deployment. All stock levels, SKUs, and orders are seeded demo data.

## What it does

- **Reserve & allocate** (`inventory_orchestration/service.py`) —
  `create_order` allocates cheapest-warehouse-first, so one order can split
  across DCs. Short stock produces a partial allocation plus a backorder
  instead of failing the order. Repeating a request with the same
  idempotency key returns the original order — no double reservation.
- **Fulfil & cancel** — fulfilment consumes the reservation and decrements
  on-hand stock; cancellation releases reserved units back to available.
  Both publish events, so shipping, billing, and replenishment services
  can react without calling this service.
- **Event bus** (`inventory_orchestration/events.py`) — models the Kafka
  topics (`inventory.reserved`, `inventory.released`,
  `inventory.allocated`, `inventory.restocked`, `order.fulfilled`,
  `order.backordered`, `order.cancelled`). Each topic has a schema, the way
  a Schema Registry enforces contracts; a bad event is rejected and never
  reaches the log. The log is append-only with sequence numbers, so
  consumers can replay from any point.
- **REST API + dashboard** (`inventory_orchestration/app.py`,
  `inventory_orchestration/ui.html`) — stock per SKU/warehouse, order
  create/fulfil/cancel, restock, the event feed, `/health`, and a
  Prometheus-format `/metrics` endpoint. The dashboard is a plain
  HTML/CSS/JavaScript page that calls the API: stock table, order form,
  order actions, live event feed.
- **Deployment** — `Dockerfile` (Python 3.12 slim), Kubernetes
  `Deployment` + `Service` manifests, and a GitHub Actions workflow that
  runs the tests and builds the image.

## Run it

```bash
python3 run_service.py          # http://localhost:8000
```

Then open the dashboard, place an order, and watch the event feed. Or
exercise the API directly:

```bash
curl -s localhost:8000/v1/inventory | python3 -m json.tool
curl -s -X POST localhost:8000/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku": "SKU-1001", "qty": 150, "idempotency_key": "demo-1"}'
curl -s 'localhost:8000/v1/events?topic=inventory.allocated'
```

## Tests

```bash
python3 -m pytest tests/ -q
```

21 tests: service allocation/backorder/idempotency, event-schema
enforcement and replay, and the live HTTP API on an ephemeral port.
