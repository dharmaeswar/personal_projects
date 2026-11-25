# Edge Data Primitives

A Python toolkit that mirrors Cloudflare's Data Primitives — D1 (managed
SQLite), Queues (messaging), and Workers KV (global key-value store) — plus
the monitoring, alerting, and log analysis a team needs to run them in
production. Built as the role project for the Cloudflare Senior Software
Engineer, Data Primitives application (Greenhouse 8398753).

Everything runs on the standard library plus pytest. SQLite is used here
exactly as D1 uses it under the hood; the queue and KV store are backed by
SQLite tables so the whole toolkit runs locally with no services.

## What it does

| Module | Primitive it mirrors | Behaviour |
|---|---|---|
| `edgeprimitives/store.py` | D1 — managed SQLite | Versioned migrations, parameterized queries only, atomic transactions, per-query timing |
| `edgeprimitives/queue.py` | Queues — messaging | At-least-once delivery, leasing with visibility timeout, retries, dead-letter queue |
| `edgeprimitives/kv.py` | Workers KV — global KV | TTL, metadata, prefix listing with cursor pagination, lagging replica (eventual consistency) |
| `edgeprimitives/monitoring.py` | Production ops | Per-operation counters/latencies, p50/p95, threshold alert rules, structured log analysis |
| `edgeprimitives/api.py` | Service API | stdlib HTTP API over all three primitives; every request timed and recorded |

## Quick start

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python run_demo.py
python -m edgeprimitives.api 8080   # then POST /enqueue, GET /metrics, ...
```

Demo run: 2 users seeded, 2 events recorded, 2 tasks processed, 0 left in
the queue, 0 dead letters, event counts cached in KV with a 300s TTL.

## Design notes

- **Store:** migrations are versioned and applied in order; a failed
  transaction rolls back completely (tested). Queries are parameterized —
  an injection string is treated as a literal value, never as SQL.
- **Queue:** leased messages hide for the visibility timeout, so a crashed
  worker's tasks become visible again instead of being lost. After
  `max_attempts` (default 3) a message moves to the dead-letter table with
  its failure reason instead of retrying forever.
- **KV:** `get(replica=True)` reads a replica that lags the primary by a
  configurable delay, so callers see the stale-read window a global KV
  really has. Expired keys return `None` and are removed by `purge_expired`.
- **Monitoring:** alert rules fire on live values (error rate, p95 latency,
  queue depth). `analyze_logs` parses structured log lines into error
  counts by code and slowest operation per endpoint — the first step in
  debugging a high-volume production incident.

## Honest limits

- Single-process SQLite, not a globally replicated store: no real multi-region
  replication, no sharding, no consensus. The replica lag is simulated.
- The queue is FIFO-ish by row id, not a distributed broker: no partitions,
  no ordering guarantees across producers, no exactly-once delivery.
- The API is a stdlib demo server (threaded, no auth, no TLS) — not a
  production service. Metrics live in memory and reset on restart.
- Written in Python, not TypeScript/Go/Rust/C++ (the languages in the
  Cloudflare posting). The design patterns — migrations, leasing, TTL,
  eventual consistency, alerting — transfer; the languages do not.
- All data is synthetic and seeded; nothing describes real Cloudflare
  traffic, customers, or systems.

## Tests

34 pytest tests, all passing: store (migrations, injection, rollback,
batching), queue (FIFO, visibility timeout, ack, retry → dead-letter),
KV (TTL expiry, metadata, pagination, replica lag), monitoring
(percentiles, error rate, alert rules, log analysis), API (full
enqueue → lease → ack flow, KV endpoints, metrics, error handling).
One real bug found and fixed by the tests: the KV pagination cursor
pointed at the first unreturned key instead of the last returned key,
which skipped a key on the next page. A second bug was found by running
the live HTTP server: SQLite connections are thread-bound, so the
threaded server needed `check_same_thread=False`.
