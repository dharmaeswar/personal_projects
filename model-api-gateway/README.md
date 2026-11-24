# Model API Gateway

An API gateway for hosted model endpoints — the layer every request to a
Model API passes through: API-key authentication, per-key rate limiting,
routing across model backends, per-request usage metering, and billing.

Built as a portfolio project for a Software Engineer, Inference Product
application (backend API layer for hosted model endpoints: auth, rate
limiting, routing, metering, billing, observability). All keys, models,
traffic, and usage are synthetic and seeded; nothing here describes a real
platform, real customers, or real billing data.

## What it does

- **Auth** (`gateway/auth.py`) — API keys with scopes
  (`models:invoke`, `usage:read`, `billing:read`), per-key tier
  (free / pro / scale), expiry, and revocation. Keys are stored as
  SHA-256 hashes, never in plain text.
- **Rate limiting** (`gateway/ratelimit.py`) — token-bucket limiter per
  key: requests-per-minute and tokens-per-minute budgets, with
  `Retry-After` guidance when a budget is exhausted.
- **Routing** (`gateway/router.py`) — a registry of model backends
  (model id → endpoints with latency and capacity). The router picks the
  healthy backend with the most capacity headroom and fails over to the
  next backend when one is down or saturated.
- **Metering & billing** (`gateway/metering.py`) — every served request
  records prompt/completion tokens and latency; usage aggregates per key
  per day, and billing prices tokens per model (per 1K tokens) into
  invoice lines.
- **Observability** (`gateway/observability.py`) — per-model latency
  histograms, error counts, p50/p95, and SLO checks (p95 latency and
  error-rate budgets) with alert rules that fire before customers notice.
- **Predictive-model serving** (`gateway/serving.py`) — a model
  registry for versioned predictive models with explicit input schemas
  (feature names, types, required flags, numeric ranges). Scoring
  validates every request against the schema (422 with details on bad
  input), serves a pinned version or the latest, and records per-model
  latency and error metrics with SLO checks. The demo scorer is a
  deterministic weighted sum through a sigmoid; a real deployment
  would load the model artifact (pickle, ONNX, or H2O MOJO) and call
  its predict method in the same place.
- **Marketplace partner intelligence** (`gateway/marketplace.py`) —
  partner data ingestion into a governed semantic layer, a
  model-serving evaluation foundation, and an agent-evaluation
  foundation, exposed as self-serve intelligence-delivery API
  endpoints (see the section below). All stores are in-memory
  stand-ins: datasets, metrics, eval runs, and traces live in
  process memory only, and all partner data is synthetic.
- **API** (`gateway/api.py`) — a small stdlib-only HTTP service:
  `POST /v1/models/{model}/completions`, `GET /v1/usage`,
  `GET /v1/billing`, `GET /health`, `GET /metrics` (Prometheus text),
  plus the serving endpoints `POST /v1/serving/models` (register),
  `GET /v1/serving/models` (list), `POST /v1/serving/models/{model}/predict`,
  `GET /v1/serving/metrics` (per-model latency/error stats),
  plus the marketplace endpoints `POST /v1/marketplace/datasets`,
  `POST /v1/marketplace/datasets/{id}/ingest`,
  `POST /v1/marketplace/semantic/metrics`,
  `POST /v1/marketplace/semantic/query`,
  `POST /v1/marketplace/evals/serving`,
  `GET /v1/marketplace/evals/serving/{run_id}`,
  `POST /v1/marketplace/evals/agents`,
  `GET /v1/marketplace/evals/agents/{run_id}`.
- **Resilience** (`gateway/resilience.py`) — the patterns that keep the
  gateway serving when a backend fails: a per-backend circuit breaker
  (closed → open → half-open, with trial calls and fail-fast while open),
  retry with exponential backoff and full jitter, a per-backend bulkhead
  that caps concurrent calls so one slow backend cannot starve the rest,
  and per-call timeouts. `ResilientRouter` ties them to the existing
  router: it picks backends in router order, runs each call through that
  backend's breaker and bulkhead with retries, and fails over to the next
  backend when one is open, full, or failing. `run_resilience_demo.py`
  shows the full arc on a synthetic two-backend model: a transient
  failure absorbed by retry, a breaker tripping and traffic failing over,
  a half-open probe closing the breaker after recovery, and a full
  bulkhead being skipped instead of queued behind.

## Marketplace partner intelligence

Built for an AWS Marketplace & Partner Services (AMPS) Data &
Analytics Engineering application: the gateway extended with the
data and evaluation foundations agents depend on.

- **Partner data ingestion** — register a partner dataset with a
  typed column schema, then ingest rows. Every row is validated
  against the schema (missing, mistyped, out-of-range, or unknown
  columns); bad rows are rejected with per-row errors and good rows
  still land, so one bad record never blocks a whole batch.
- **Governed semantic layer** — define a metric once (dataset +
  column + aggregation: sum, avg, count, min, max) and query it by
  name with filters. Every answer carries lineage (dataset, column,
  aggregation, filters) so agents and teams share one trustworthy
  definition instead of writing their own SQL.
- **Model-serving evaluation foundation** — run a served model
  against eval cases (features + the prediction range it must land
  in). Each case records the serving version and prediction; the run
  reports a pass rate and a pass/fail gate against a minimum pass
  rate. Validation failures and unknown models fail their case.
- **Agent-evaluation foundation** — run an agent against eval cases
  (prompt + text the answer must contain). Each case records the
  agent's trace (retrieve → reason → respond) so failures can be
  debugged step by step, and the run reports a pass rate and gate.
  The built-in agent is a deterministic stand-in that answers only
  from a small governed-knowledge table; a real agent would retrieve
  from the semantic layer and call tools, and would be evaluated the
  same way.

Example (seeded key `sk-demo-pro-1`):

```bash
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "partner-sales", "name": "Partner Sales", "owner_partner": "demo-partner",
       "columns": [{"name": "partner", "type": "string"}, {"name": "region", "type": "string"},
                   {"name": "revenue", "type": "number"}, {"name": "active", "type": "boolean"}]}' \
  http://127.0.0.1:8000/v1/marketplace/datasets
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"rows": [{"partner": "acme", "region": "us", "revenue": 100, "active": true}]}' \
  http://127.0.0.1:8000/v1/marketplace/datasets/partner-sales/ingest
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"name": "total_revenue", "dataset_id": "partner-sales", "column": "revenue", "aggregation": "sum"}' \
  http://127.0.0.1:8000/v1/marketplace/semantic/metrics
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"metric": "total_revenue", "filters": {"region": "us"}}' \
  http://127.0.0.1:8000/v1/marketplace/semantic/query
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"agent": "marketplace-intelligence-agent",
       "cases": [{"prompt": "How did partner revenue trend?", "expected_contains": "revenue grew"}]}' \
  http://127.0.0.1:8000/v1/marketplace/evals/agents
```

## Run it

```bash
pip install -r requirements.txt   # pytest only; the service is stdlib-only
python run_service.py             # serves on :8000 with seeded keys and models
```

Then, with a seeded key (printed by `run_service.py`, e.g. `sk-demo-pro-1`):

```bash
curl http://127.0.0.1:8000/health
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize freight rail delays.", "max_tokens": 64}' \
  http://127.0.0.1:8000/v1/models/llama-4-scout/completions
curl -H "Authorization: Bearer sk-demo-pro-1" http://127.0.0.1:8000/v1/usage
curl -H "Authorization: Bearer sk-demo-pro-1" http://127.0.0.1:8000/v1/billing

# Predictive-model serving (seeded demo model: churn-risk v1.2.0)
curl -H "Authorization: Bearer sk-demo-pro-1" http://127.0.0.1:8000/v1/serving/models
curl -X POST -H "Authorization: Bearer sk-demo-pro-1" \
  -H "Content-Type: application/json" \
  -d '{"features": {"tenure_months": 24, "monthly_spend": 450, "support_tickets": 1, "is_enterprise": false}}' \
  http://127.0.0.1:8000/v1/serving/models/churn-risk/predict
curl -H "Authorization: Bearer sk-demo-pro-1" http://127.0.0.1:8000/v1/serving/metrics

## Docker & Kubernetes

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t model-api-gateway .
docker run -p 8000:8000 model-api-gateway
kubectl apply -f k8s/   # 2-replica Deployment + ClusterIP Service, probes on /health
```

## CI

`.github/workflows/ci.yml` runs the pytest suite on every push/PR touching
this subfolder, then builds and pushes a multi-arch (amd64 + arm64) image to
ghcr.io. GitHub Actions only runs workflows from the repository root, so to
enable it copy that file to `<repo-root>/.github/workflows/model-api-gateway-ci.yml`.

## Tests

```bash
python -m pytest tests/ -q
```

Tests cover key verification, scopes, expiry and revocation; token-bucket
refill and exhaustion; router selection, failover and saturation; metering
aggregation and billing math; p50/p95 and SLO alerts; the API
endpoints (including unauthenticated, over-limit, and unknown-model
rejections); and predictive-model serving — registry versioning and
duplicate rejection, schema validation (missing, mistyped, out-of-range,
and unknown features), deterministic scoring, pinned-version serving,
and per-model latency/error metrics with SLO evaluation — and
marketplace partner intelligence: schema-validated ingestion with
per-row rejection, governed metric definition and filtered queries
with lineage, serving-eval gates (pass, fail, and validation-failure
cases), agent-eval gates with traces, auth checks, and an HTTP
end-to-end round trip.
