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
- **API** (`gateway/api.py`) — a small stdlib-only HTTP service:
  `POST /v1/models/{model}/completions`, `GET /v1/usage`,
  `GET /v1/billing`, `GET /health`, `GET /metrics` (Prometheus text).

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
```

## Tests

```bash
python -m pytest tests/ -q
```

Tests cover key verification, scopes, expiry and revocation; token-bucket
refill and exhaustion; router selection, failover and saturation; metering
aggregation and billing math; p50/p95 and SLO alerts; and the API
endpoints (including unauthenticated, over-limit, and unknown-model
rejections).
