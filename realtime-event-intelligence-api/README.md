# Real-Time Event Intelligence API

A Python backend service for a real-time event and threat intelligence
platform: it ingests streaming event signals, scores them for severity,
dedupes repeats, persists them in SQL, and serves alerts over a REST API
guarded by bearer-token auth (OAuth2-style scopes).

Built as a portfolio project for a Software Engineer III, Backend
application (real-time streaming data, microservices, SQL databases,
identity and access management). All event data is synthetic and seeded;
no real events, sources, or alerts are involved, and nothing here
describes a real platform or a real threat posture.

## What it does

- **Stream** (`event_intel/stream.py`) — an in-memory streaming topic
  with partitions, offsets and consumer-group tracking, modelled on a
  Kafka topic: producers publish event signals, consumers read in offset
  order and commit offsets per group.
- **Scoring** (`event_intel/scoring.py`) — a deterministic severity score
  (0–100) from source reliability, keyword severity, corroboration count
  and recency decay. Scores >= 70 raise a critical alert, >= 40 a watch.
- **Dedupe** (`event_intel/store.py`) — every event gets a fingerprint
  from its source id, normalized text and event type; repeats are dropped
  and counted instead of stored twice.
- **Store** (`event_intel/store.py`) — SQLite tables for events and
  alerts, with queries for alerts by minimum severity and by id.
- **Auth** (`event_intel/auth.py`) — bearer tokens with scopes
  (`events:write`, `alerts:read`) and expiry, the way an OAuth2/OIDC
  access token works: expired tokens and wrong scopes are rejected.
- **Windowing** (`event_intel/windowing.py`) — Flink-style tumbling
  windows over event time, with a watermark that closes windows and
  an allowed-lateness bound: events arriving after their window
  closed are counted as late and dropped, never silently merged.
- **Checkpointing** (`event_intel/checkpoint.py`) — signal schema
  validation, a dead-letter queue for malformed records, exactly-once
  handling that skips redelivered records, and offset snapshots so a
  restarted consumer resumes where it stopped instead of replaying
  the whole topic. The pipeline (`event_intel/pipeline.py`) now
  validates every record, routes bad ones to the DLQ, and buckets
  scored events into tumbling windows.
- **API** (`event_intel/api.py`) — a small HTTP service (stdlib only):
  `POST /v1/events` ingests one signal, `GET /v1/alerts` lists alerts,
  `GET /v1/alerts/{id}` fetches one, `GET /health` is the liveness check.

## Streaming at scale (new, Nov 2026 — for the Zscaler Senior SDE, Data & APIs application)

- **Anomaly detection** (`event_intel/anomaly.py`) — statistical and
  rules-based detectors over windowed telemetry counts: z-score against
  a rolling baseline, a median/MAD detector robust to spikes already in
  the baseline, and rules (absolute ceiling, rate-of-change). Detectors
  wait for at least 5 history points before flagging, so a 2-point
  baseline cannot produce a false spike. Anomalies from different
  sources in the same window are correlated into one signal.
- **Backpressure & cost** (`event_intel/backpressure.py`) — bottleneck
  triangulation across producer / broker / consumer / stateful-operator
  stages (lowest drain ratio wins, ties break on queue depth); a
  backpressure controller that recommends scale-consumers, tune-consumer
  or shed-load with the reason attached; and a planning cost model for
  cost per TB/day (ingest / retention / scan split).
- **Versioned APIs** (`event_intel/apiversion.py`) — API contracts with
  additive-only evolution checks (removals and type changes are named
  violations), version negotiation (highest supported at or below the
  requested version), and a deprecation registry with removal versions.

```bash
python run_scale_demo.py   # detectors + correlation + bottleneck + backpressure + API compat
```

Demo results: 4 anomalies found across the detectors; 1 correlated
signal (two sources spiking in window 10, critical); bottleneck is the
consumer (drain ratio 0.53, 98% utilized, queue 45,000); backpressure
recommends scaling consumers; v1 → v2 is backward compatible
(additive `severity` field); 10 TB/day costs $1,060/day with retention
dominating. Cost constants are illustrative planning numbers, not
measured cloud prices, and the detectors are statistical/rules-based
stand-ins — no production ML model is claimed.

## Run it

```bash
pip install -r requirements.txt   # pytest only; the service is stdlib-only
python run_service.py             # seeds a stream, runs the consumer, serves on :8000
```

Then, with a token minted by the service log (or any `alerts:read` token
from `event_intel.auth.mint_token`):

```bash
curl http://127.0.0.1:8000/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/v1/alerts?min_severity=70
curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"source_id":"wire-1","event_type":"outage","text":"power outage downtown","reliability":0.9,"corroborations":3}' \
  http://127.0.0.1:8000/v1/events
```

## Tests

```bash
python -m pytest tests/ -q
```

77 tests cover the stream offsets, the scoring bands and decay, dedupe
counts, the SQL store, token expiry and scopes, and the API endpoints
(including unauthenticated and wrong-scope rejections), plus the new
anomaly detectors, backpressure/cost model, and API versioning.
