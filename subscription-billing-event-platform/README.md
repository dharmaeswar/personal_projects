# Subscription Billing Event Platform

A wholesale subscription billing and distribution service in the shape of
Amazon Fuse: third-party enterprises (partners such as Prime, Music, Video)
offer subscription services through global billing partners, and this
platform provisions entitlements, routes billing events, and bills,
renews, and cancels with idempotent, retry-safe handlers.

## What it models (from the Amazon Fuse posting)

- **Low-latency services** for frontend, middle tier, and backend:
  an in-memory entitlement index answers "does this subscriber have an
  active plan?" in microseconds, with p50/p95 latency tracking.
- **Microservices on AWS primitives**: a DynamoDB-shaped entitlement
  store (partition + sort key, conditional writes, TTL), SNS-shaped
  topics fanning out to SQS-shaped queues (deduplication, FIFO ordering
  per subscriber, dead-letter queue), and Lambda-shaped handlers.
- **Billing and distribution**: partner onboarding with plans, idempotent
  provisioning, charges, renewals, prorated partial periods, dunning,
  and cancellation — replays never double-charge or double-provision.

## Layout

- `subscription_billing/store.py` — entitlement store (DynamoDB shape)
- `subscription_billing/events.py` — topic/queue event bus (SNS/SQS shape)
- `subscription_billing/billing.py` — partner onboarding + billing handlers
- `subscription_billing/api.py` — low-latency entitlement lookup
- `run_billing.py` — end-to-end demo
- `tests/` — pytest suites for the store, bus, billing, and lookup

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_billing.py
```

Demo output: 2 partners onboarded, 3 subscriptions provisioned,
2 charges, 1 renewal, 1 cancellation, 0 DLQ messages, p95 lookup
under 1 ms. All data is synthetic and local; nothing here claims
production use.
