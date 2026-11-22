# LLM Training Data Infrastructure

A Python service for the data infrastructure behind LLM training: a
dataset catalog, batch and streaming ingestion with content-hash
deduplication, quality gates with quarantine, lineage tracking, and
dashboards for catalog health, ingestion throughput and pipeline health.

Built as a portfolio project for a Software Engineer, Data
Infrastructure application (distributed training pipelines, multimodal
data catalogs, intelligent processing over large corpora). All datasets,
records and owners are synthetic demo data; nothing here describes a
real platform or real training data. Python standard library only — no
third-party runtime dependencies.

## What it does

- **Catalog** (`llm_data_infra/store.py`) — register datasets by
  modality (text, image, audio, multimodal) with immutable versions;
  search the catalog by name or description.
- **Ingestion** (`llm_data_infra/ingestion.py`) — batch ingest and a
  streaming consumer loop with the same gates: SHA-256 content-hash
  dedup per dataset version, quality gates, quarantine instead of
  silent drops, and a per-run job record with counts.
- **Quality gates** (`llm_data_infra/quality.py`) — completeness,
  text-length bounds, allowed modality, and a PII-pattern scan (email /
  SSN-like strings) that quarantines the record with the failure reason.
- **Lineage** — provenance edges from parent dataset version to child
  (e.g. `dedup+filter`, `caption-join`) so any derived dataset can be
  traced back to its sources; every state change is audit-logged.
- **Dashboards** (`llm_data_infra/service.py`) — per-dataset stats
  (records, accepted, quarantined, dedup rate, quality failures,
  lineage edges) and an ingestion summary with accept rate and
  pipeline health.
- **HTTP API** (`llm_data_infra/server.py`) — stdlib `http.server`
  JSON API plus a dashboard page; no framework needed.

## Run it

```bash
python -m llm_data_infra     # serves http://127.0.0.1:8000
python run_demo.py            # seeds synthetic data, prints the summary
python -m pytest tests/ -q    # 8 tests
```

Example API flow:

```bash
curl -X POST localhost:8000/api/datasets \
  -d '{"name":"webtext-v3","modality":"text","owner":"data-platform"}'
curl -X POST localhost:8000/api/datasets/1/versions -d '{"version":"3.0"}'
curl -X POST localhost:8000/api/ingest/batch \
  -d '{"dataset_id":1,"version":"3.0","modality":"text","records":[{"text":"..."}]}'
curl localhost:8000/api/dashboard
```

Demo seed: 2 datasets, 7 records ingested — 4 accepted, 1 duplicate
dropped by content hash, 2 quarantined (too short, PII pattern);
accept rate 0.57 on the deliberately dirty demo feed.
