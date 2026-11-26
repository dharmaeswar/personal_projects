# Product Config API Service

An API-first product-configuration service: modular, configurable product
capabilities exposed as a REST microservice, built the way a cloud-native
internal tooling team would build one — small Lambda-style handlers, a
DynamoDB-style key-value store, a Step Functions-style publish workflow,
Terraform infrastructure as code, and a CI pipeline that runs the tests.

Built as a portfolio project for the Nike — Software Engineer II, CP&I
(Consumer Product & Innovation) application (Job ID R-97791): the team
builds modular, configurable, API-first tooling for internal product
creation, consumed by modern single-page web apps. All products,
attributes, and traffic here are synthetic. Nothing describes a real
Nike system, real products, or real data.

## What it does

- **Versioned configs** (`product_config/models.py`) — a product config
  is a set of named modules (e.g. `materials`, `sizing`, `colourways`),
  each with typed attributes (string / number / boolean / enum).
  Validation rejects bad slugs, duplicate names, and enum values outside
  their option list.
- **Store** (`product_config/store.py`) — DynamoDB-style key-value store
  (partition key `product_id`, sort key `version`) backed by a JSON file
  locally, so the service runs with no AWS account. Supports latest and
  latest-published lookups.
- **Publish workflow** (`product_config/service.py`) — a Step
  Functions-style state machine: `draft -> review -> published`, with
  validation enforced before review. Publishing keeps versions immutable.
- **Config assistant** (`product_config/ai_assist.py`) — a deterministic,
  rule-based assistant that suggests defaults for unset attributes,
  flags conflicting attribute pairs, and scores config completeness.
  Every suggestion names the rule behind it.
- **Lambda handlers** (`product_config/handlers.py`) — API
  Gateway-style event handlers (`create`, `get`, `get published`,
  `publish`, `suggest`) that run unchanged behind API Gateway or locally.
- **REST API** (`product_config/api.py`) — stdlib-only HTTP server
  exposing the handlers as REST endpoints.
- **Infrastructure** (`infra/main.tf`) — Terraform for the DynamoDB
  table, four Lambda functions, an HTTP API, and the Step Functions
  publish state machine. Not applied; code only.
- **CI** (`.github/workflows/ci.yml`) — runs pytest and smoke-tests the
  API server on every push.

## API

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/v1/products` | Create a config (version 1, draft) |
| GET | `/v1/products/{id}` | Latest version (`?version=N` for one) |
| GET | `/v1/products/{id}/published` | Latest published version |
| POST | `/v1/products/{id}/publish?version=N` | Run the publish workflow |
| GET | `/v1/products/{id}/suggest?version=N` | Defaults, warnings, completeness |
| GET | `/health` | Liveness check |

## Run it

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
CONFIG_STORE_PATH=./configs.json python run_api.py
```

Then, for example:

```bash
curl -X POST localhost:8080/v1/products -d '{
  "product_id": "runner-x1", "name": "Runner X1",
  "modules": [
    {"name": "materials", "attributes": [
      {"name": "upper-material", "type": "enum", "value": "engineered-mesh",
       "options": ["engineered-mesh", "suede", "leather"], "required": true}]},
    {"name": "sizing", "attributes": [
      {"name": "size-run", "type": "enum", "value": "US 7",
       "options": ["US 7", "US 8", "US 9"], "required": true}]}
  ]}'
curl -X POST "localhost:8080/v1/products/runner-x1/publish?version=1"
curl localhost:8080/v1/products/runner-x1/published
curl localhost:8080/v1/products/runner-x1/suggest
```

## Fare configuration example (Uber — Software Engineer II, Backend, Fares Platform)

`examples/fare_config.json` is a fare configuration built on the same generic service: modules for base fare,
per-mile / per-minute rates, a surge multiplier, and the service area. Creating it, publishing it through the
draft -> review -> published workflow, and serving only the published version is exactly the problem a fares
platform solves: fare rules change often, must be validated before they go live, and must be versioned so a bad
change can be rolled back by republishing the previous version. `tests/test_fare_config.py` covers that flow:
publish, version bump with a fare change, invalid surge multiplier rejected, duplicate module rejected, illegal
transition rejected, and the full HTTP round trip. All fare values are synthetic examples. Nothing here describes
a real Uber system, real fares, or real trip data.

## Skills used

Only skills Dharma has verified: Python, REST APIs, JSON data modelling,
pytest, Terraform, AWS concepts (Lambda, Step Functions, DynamoDB, S3),
GitHub Actions CI, Linux, Bash. This project does not claim React,
Angular, Vue, Mocha, Jasmine, or Jest experience.
