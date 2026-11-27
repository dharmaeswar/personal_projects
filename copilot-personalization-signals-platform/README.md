# Copilot Personalization Signals Platform

A portfolio project for a **Senior Software Engineer — Data, Personalization
(Microsoft AI / Copilot)** role. It builds the data platform a Copilot
personalization team runs: ingest telemetry, product-usage and
experimentation events, build governed user-context data models, and serve
low-latency personalization signals through an API — in batch and in real
time — with privacy and user-control checks on every signal served.

**All data is synthetic and seeded (seed 42).** No real user, Copilot, or
Microsoft data is used, and nothing here is a claim about any real system.
No cloud services are actually called: the lake is local JSON files, the
"Kafka topic" is an in-memory queue the code names, the "Spark job" is
plain-Python aggregation that names the Spark operation it mirrors, and
the "Azure" deployment is a declarative manifest. The code says so
wherever it matters. Python standard library only — no third-party
runtime dependencies.

## Problem statement

Copilot should feel like *your* Copilot — responsive to preferences,
workflows and goals — but the signals that make that possible live in
three messy streams: telemetry events, product-usage events, and
experimentation assignments. Producers ship malformed rows, batches get
re-delivered, late events arrive, and some signals must never be served
because the user did not consent to that category. Downstream (the
Copilot runtime) needs one governed place to ask "what do we know about
this user, right now?" — not raw event files.

This project fixes that with a signals platform:

- **Ingest** — a Kafka-style event queue (in-memory; the code names the
  Kafka topic it mirrors) with per-batch validation. Bad rows are
  quarantined with the rule that fired (missing user id, unknown event
  type, future timestamp, negative duration, unknown experiment arm);
  re-delivered events collapse on `event_id` (idempotent, exactly-once
  effect). A retry path re-checks corrected rows and promotes the ones
  that pass.
- **Batch engine** — a Spark-style job (plain Python; every operation
  names its Spark equivalent, e.g. `groupBy`, `window`, `join`) that
  builds per-user context: top workflows, preferred features, goal
  affinity, and experiment-arm membership, with recency-weighted scores.
- **Real-time engine** — a sliding-window scorer over the last hour of
  events that boosts signals the user is acting on right now and decays
  stale ones, then merges with the batch signals.
- **Data models** — a governed user-context model (`UserContext`) with
  typed fields, consent flags per signal category, and lineage (every
  signal records the event ids and job run that produced it).
- **Serve** — a low-latency read API (stdlib `http.server`, JSON):
  `GET /signals/<user_id>` returns the merged, consented signals for a
  user; `GET /health` reports store and pipeline state. Consent is
  enforced at serve time: a category the user opted out of is never
  returned, and raw PII fields (email, free text) are redacted before
  any signal leaves the store.
- **Orchestrate** — a DAG runner (ingest → validate → batch → quality →
  publish) with topological ordering, one retry for transient failures,
  and resume by run id: a re-run with the same run id skips tasks that
  already succeeded with the same inputs.
- **Quality** — completeness, uniqueness, timestamp/freshness, and
  reconciliation checks (signals reconcile back to accepted events);
  a failed check blocks publish.
- **Privacy** — consent is a first-class input: users opt in/out per
  category (usage, telemetry, experimentation); opted-out categories
  are excluded from batch aggregates and from the serving API, and an
  audit log records every serve decision.

## Layout

```
signals/
  models.py        Event, UserContext, Signal, Consent dataclasses
  store.py         JSON-file store (events, profiles, signals, audit log)
  ingest.py        validation, quarantine, dedupe, retry path
  privacy.py       consent checks, PII redaction, serve-time filtering
  batch.py         Spark-style batch personalization engine
  realtime.py      sliding-window real-time scorer + merge
  orchestration.py DAG runner: order, retry, resume, run state
  quality.py       data-quality checks; publish gate
  serve.py         stdlib HTTP API (signals + health) + event ingest
  seed.py          deterministic synthetic events (seed 42)
run_demo.py        end-to-end run: seed -> DAG -> serve a sample user
tests/             pytest suite (ingest, batch, realtime, privacy,
                   orchestration, quality, serve)
```

## Run it

```bash
python run_demo.py
python -m pytest tests/ -q
```

`run_demo.py` seeds 240 synthetic events across 8 users over 7 days,
runs the DAG, and prints the merged signals served for one sample user
(plus the signals withheld by consent). The seed plants deliberately
broken rows (missing user, duplicate id, unknown type, future timestamp,
negative duration) so the quarantine and dedupe paths run on every
execution, and one user with telemetry consent off so the privacy path
runs too.

## Design notes

- The store is a local JSON file, not a cloud warehouse; the "Kafka
  topic" is an in-memory queue; the batch job is plain Python that names
  its Spark equivalent per operation, so the same logic maps to
  PySpark/Databricks. The serving API is stdlib `http.server`, not a
  deployed Azure service.
- Scoring is deterministic and rule-based (recency-weighted counts and
  affinities), not an ML model. Demonstrated on seeded synthetic data,
  not at production scale.
- Not implemented: real distributed deployment, multi-region
  replication, real auth/rate-limiting, real experiment-assignment
  service, or a production feature store.

## Honest limits

All events, users, preferences and signals are synthetic examples;
nothing describes a real Copilot user, real telemetry, or a real
Microsoft system. Latency is measured in-process (serve reads from the
local JSON store), not against a production SLA. Consent categories are
the three in the seed (usage, telemetry, experimentation); no real
privacy review is represented here.
