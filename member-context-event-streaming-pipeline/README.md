# Member Context Event Streaming Pipeline

A portfolio project for an **Oscar Health — Senior Data Engineer II**
role. It builds the member-context and event-data foundation the role
asks for: member engagement events (web, app, health-AI agent,
outbound) stream through a Kafka-style topic into point-in-time-correct
member context, with data contracts, data quality, lineage, and curated
layers for ML inference and LLM consumption — the foundation a
personalization platform (recommendation, ranking, next-best-action,
experimentation) is built on.

**All data is synthetic and seeded (seed 42).** No real member, health,
or Oscar data is used, and nothing here describes a real company's
traffic or a production pipeline.

## Runs locally, without Kafka or any cloud service

No Kafka cluster, Dataflow, Kinesis, or cloud account is used here, so
the pipeline runs locally with Python's standard library. The broker is
an in-memory model of Kafka semantics (topics, partitions keyed by
`member_id`, offsets, consumer groups, committed offsets, lag), and
every module names the real Kafka / streaming operation it mirrors.
It does **not** pretend a cluster or cloud run happened.

## Problem statement

A personalization platform is only as good as its member context.
Engagement events arrive messy: producers re-deliver events, some
arrive hours late, a few rows are just wrong (missing fields, unknown
types, future timestamps, negative values). The obvious way to build
context — "everything we know about this member" — leaks the future
into training and serving, and flatters the model offline. Downstream
teams (predictive models, the health-AI agent, outbound engagement)
need context they can trust: deduplicated, quality-gated,
point-in-time correct, traceable to its source topic and contract
version, and shaped for both ML inference and LLM consumption.

## What it does

| Module | Role duty it maps to |
|---|---|
| `member_context/events.py` | **Ingestion** — seeded synthetic member engagement events (web page views, app opens, searches, plan browsing, care search, agent messages, outbound clicks, benefit views, claim checks) with ~2% re-deliveries, ~2% late arrivals, ~3% contract-breaking rows |
| `member_context/broker.py` | **Kafka semantics** — topics with 6 partitions keyed by `member_id`, offsets, consumer groups with committed offsets and lag |
| `member_context/contracts.py` | **Data contracts** — versioned per-event-type contracts (required fields, channels, value ranges); bad rows quarantined with the rule that fired, never dropped silently |
| `member_context/streaming.py` | **Stream processing** — 30-minute-gap sessionization; point-in-time member context (features from events strictly *before* the as-of time, no leakage); 7-day windowed aggregates |
| `member_context/context_layers.py` | **Curated layers** — `member_context_snapshot` feature rows for ML inference; `llm_context_document` retrieval-ready structured context per member; action/journey catalogue (8 actions, 5 journeys) |
| `member_context/lineage.py` | **Lineage & SLOs** — per-layer lineage (source topic, contract version, row counts, SHA-256 fingerprint); freshness (p95 ingest lag, 15-min objective) and completeness (95% objective) SLOs evaluated per run |
| `member_context/orchestration.py` | **Orchestration** — ingest → consume → validate → dedupe → sessionize → snapshot → curate → lineage → SLOs, with a run manifest |

## Skills used

Only skills Dharma has verified: Python, SQL, Kafka (used at AMDOCS —
Spring Boot + Kafka event pipelines streaming usage events between
billing and rating systems), PyTest, Git, Linux, Bash. This project
does **not** claim production Kafka operation, Google Cloud Dataflow,
or AWS Kinesis experience — the broker is a local model, the README
says so, and the resume does not list Dataflow or Kinesis.

## Demo run (seed 42, 40 members)

```
$ python3 run_pipeline.py
produced 1071, consumed 1071, valid 1017, quarantined 29, duplicates dropped 25
sessions 930, snapshot rows 40, LLM documents 40
SLOs: freshness p95 4.88 min (objective 15) — met; completeness 0.9723 (objective 0.95) — met
```

The seeded run deliberately includes late arrivals (up to 12 hours)
and contract-breaking rows, so the SLOs are percentile-based and set
against that known bad-row rate: a run fails only if lag or bad rows
genuinely rise. Every layer carries a lineage entry with a SHA-256
fingerprint of its content.

## How to run

```bash
pip install -r requirements.txt   # pytest only; runtime is stdlib-only
python3 run_pipeline.py           # end-to-end demo, prints the run manifest
python3 -m pytest tests/ -q       # 17 tests
```

## Layout

```
member_context/
  events.py         synthetic event generator (seeded)
  broker.py         in-memory Kafka-style broker + consumer groups
  contracts.py      versioned data contracts + quality checks / quarantine
  streaming.py      sessions + point-in-time member context + windows
  context_layers.py ML snapshot rows + LLM context documents + catalogue
  lineage.py        lineage entries, fingerprints, SLO evaluation
  orchestration.py  end-to-end run + manifest
run_pipeline.py     demo entry point
tests/              pytest suites (events, broker, contracts, streaming, layers, SLOs)
```
