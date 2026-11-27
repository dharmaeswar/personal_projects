# Agentic Integration Surface

An MCP-style integration layer that exposes legacy-application modernization
capabilities as versioned, well-specified tools an AI agent can discover,
invoke, and orchestrate — built for the **MongoDB — Software Engineer 3,
Agentic Integrations (AMP)** role (Req 4273608317).

A NEW project: no existing repo subfolder builds an *integration surface*.
The closest projects cover different problems — `agent-engine-runtime` runs
agents (execution, memory, retrieval, governance), `agentic-code-migration-evaluator`
scores migrations, and `agent-security-validation-suite` is an adversarial eval
harness. None defines tool contracts, API clients/adapters, auth-context
propagation, observability, or SDK/CLI surfaces for a modernization platform.

All data is synthetic and seeded. No network calls, no model calls, no
credentials. Standard library only, plus pytest for tests.

## What it does

- **Tool registry** (`integration_surface/tools.py`) — versioned tools with
  JSON-schema input contracts, required scopes, and deprecation. v1 keeps
  working after v2 ships (backward compatibility); every call is validated,
  authorized, and observed.
- **Contracts** (`integration_surface/contracts.py`) — input validation
  (types, required fields, enums, bounds), machine-readable error codes, and
  explicit partial-success semantics for batch calls: some items may succeed
  while others fail, and that is reported as partial success, never as a
  silent or full success.
- **Caller context** (`integration_surface/context.py`) — user, tenant, and
  scopes propagate unchanged across every boundary, so an agent-invoked call
  never carries more privilege than the user it acts for. Tenant context is
  immutable; cross-tenant access is denied.
- **Modernization adapters** (`integration_surface/adapters.py`) — the
  capabilities behind the tools, over synthetic legacy schemas
  (`orders`, `billing`): schema analysis (tables, join depth, embed
  candidates), relational-to-document transformation (type mapping, embed vs
  reference strategy), migration dry-run (per-table outcomes), and
  migrated-data validation (row counts, duplicate keys, sample checks).
- **Model stub** (`integration_surface/adapters.py`) — a seeded deterministic
  stand-in for a model call, so nondeterministic behaviour can be tested
  reproducibly: the same seed always gives the same suggestion, and a flaky
  mode fails a fixed number of calls so retry logic is exercised. Failed
  model calls are retried a bounded number of times, then reported as a
  retryable error with the attempt count.
- **Observability** (`integration_surface/observability.py`) — one structured
  log line, one trace span, and one metrics observation per call (latency
  percentiles, error counts, recent failures, actionable diagnostics).
- **SDK + CLI** (`integration_surface/sdk.py`, `integration_surface/cli.py`) —
  a typed client and a command-line tool over the same surface, the way an
  agent framework or a developer would consume it.

## Tools exposed

| Tool | What it does |
|---|---|
| `amp.analyze_schema` v1 | Summarize a legacy schema: tables, join depth, embed candidates |
| `amp.transform_table` v1/v2 | Map one relational table to a MongoDB document shape |
| `amp.transform_batch` v1 | Transform several tables; per-item success/failure reported |
| `amp.dry_run_migration` v1 | Simulate a migration plan; per-table outcomes |
| `amp.validate_migrated` v1 | Check migrated docs vs source: counts, keys, samples |
| `amp.suggest_mapping` v1 | Model mapping suggestion with bounded retries |

## Test coverage (39 passed, 0 failed)

Contract validation (missing/wrong-type/unknown fields, enums, bounds, nested
objects), partial success (mixed / all-ok / all-failed), context propagation
and immutability, scope enforcement, cross-tenant denial, versioning
(v1 still works after v2), model retry-then-succeed and give-up-after-retries,
same-seed determinism, handler-crash isolation (internal error, no stack
leak), adapter outcomes (type mapping, embed candidates, batch partial
success, dry-run mixed outcomes, validation pass/fail), metrics percentiles,
diagnostics, SDK end-to-end flow, and CLI success/failure exit codes.

## Honest limits

The schemas, rows, and model suggestions are seeded fixtures, not a real
modernization platform. The "model" is a deterministic stub, not an LLM;
retry behaviour is verified against the stub, not a live model. The registry
is in-memory and single-process — it demonstrates the integration semantics
(contracts, context propagation, observability), not a scaled-out service.

## How to run

```bash
pip install -r requirements.txt   # pytest only; app code is stdlib-only
python -m pytest tests/ -q        # 39 tests
python run_demo.py
python -m integration_surface.cli list-tools
python -m integration_surface.cli analyze orders
python -m integration_surface.cli transform orders customers --strategy embed
python -m integration_surface.cli dry-run orders
python -m integration_surface.cli suggest "map the orders table" --seed 7
```
