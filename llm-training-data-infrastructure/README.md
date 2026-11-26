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
- **Parallel sharded loading** (`llm_data_infra/loader.py`) — records
  are assigned to shards deterministically by content hash; quality-gate
  evaluation runs in parallel across shards on a worker pool, then a
  single-threaded commit phase inserts them (one writer avoids
  database-lock contention, and content-hash dedup makes re-ingest
  idempotent). Each shard reports its own counts.
- **Checkpoint / resume** (`llm_data_infra/checkpoint.py`) — a small
  JSON checkpoint is written after every shard commits. If the process
  dies mid-run, the next run loads only the shards not yet checkpointed
  as done, so no shard is loaded twice and no record is inserted twice.

## Run it

```bash
python -m llm_data_infra     # serves http://127.0.0.1:8000
python run_demo.py            # seeds synthetic data, prints the summary
python run_training_loader.py # parallel sharded load, crash, resume; writes training_loader_report.json
python -m pytest tests/ -q    # 13 tests
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

Training-loader demo (`run_training_loader.py`): 220-record synthetic
corpus, 4 shards, crash simulated after 2 shards, resume from
checkpoint — crash + resume totals equal a clean single-pass load
exactly (200 accepted, 10 duplicates, 10 quarantined), with no record
stored twice. See `training_loader_report.json`.

## Honest limits

- The loader is a CPU-bound, in-process pipeline on SQLite: gate
  evaluation runs in parallel, but the commit phase is single-threaded
  by design. It models sharding, parallelism and fault-tolerant resume
  for training-data loading; it is not a distributed system and claims
  no GPU, CUDA/Triton kernel, or multi-node training work.
