# Identity Extensibility Actions Runtime

A local model of the Auth0 Actions platform — the extensibility runtime
that runs tenant-supplied code at points in the login and token pipeline
(pre-user-registration, post-login, pre-token-issuance, ...). It is built
as a portfolio project for the **Okta — Senior Software Engineer,
Actions (Auth0)** role (Greenhouse 8415766): an ultra-low latency,
secure, scalable platform for untrusted code execution.

All data is synthetic and local. Nothing here describes a real Okta or
Auth0 system, real tenant, or real user.

## Problem statement

When thousands of tenants run custom code inside your login flow, the
platform team has to solve problems no single tenant sees:

- **Untrusted code execution** — tenant code must run without ever
  getting native execution, network access, or file access.
- **Tenant isolation** — one tenant's actions, secrets, and cache must
  never leak into or starve another tenant's.
- **Latency budget** — an action in the login path has milliseconds,
  not seconds; a runaway action must be cut off, not allowed to hang
  the login.
- **Fail-open vs fail-closed** — a broken analytics action after login
  should not lock users out, but a broken action before token issuance
  must never let a bad token through.
- **Observability** — every invocation needs metrics and an audit trail
  that can prove what ran and what it decided.

## What it does

| Module | What it models |
|---|---|
| `actions_runtime/events.py` | Triggers (pre-user-registration, post-login, pre-token-issuance, ...) and the auth event each action receives |
| `actions_runtime/actions.py` | Action model + registration-time validation: only allow-listed step ops, max 50 steps, value size caps |
| `actions_runtime/sandbox.py` | Sandboxed step interpreter: op budget (timeout), claim-size cap, tenant-scoped secrets/cache, no network/file/eval — the only outbound call is `call_api` against an in-process endpoint registry |
| `actions_runtime/tenancy.py` | Tenant registry, per-tenant quotas, cross-tenant access denial |
| `actions_runtime/secrets.py` | Per-tenant secret store; audit/log lines carry the secret name only, values redacted |
| `actions_runtime/cache.py` | Per-tenant TTL cache, namespaced so tenants cannot read or poison each other's entries |
| `actions_runtime/pipeline.py` | Runs a tenant's deployed actions for a trigger in order; fail-closed triggers deny the flow on action error/timeout, fail-open triggers log and continue |
| `actions_runtime/observability.py` | Per-action metrics (invocations, errors, denials, timeouts, p95) and a hash-chained, append-only audit log |
| `actions_runtime/authz.py` | OpenFGA-style authorization modeling: type definitions with direct and union (userset-rewrite) relations, a relationship-tuple store, group membership, `check` with cycle guard and depth cap (fails closed), `list_objects`; `ciam_model()` ships viewer < editor < admin |
| `actions_runtime/api.py` | REST-style service layer (create tenant, register/deploy action, store secret, invoke trigger, health) with idempotency keys on mutating calls; `authorize()` checks a user against the tuple store, tenant-scoped, and audits the decision |
| `actions_runtime/k8s.py` | Kubernetes Deployment / Service / HPA manifests as data (3 replicas, anti-affinity across zones, 500m/512Mi requests, 2000m/2Gi limits, HPA 3–30 pods at 70% CPU) |
| `examples/post_login_action.ts` | Sample tenant Action in TypeScript, as Actions are authored — a fixture only, not executed by the local runtime |

## Demo results (`python run_demo.py`)

- Acme post-login action: login allowed, custom claim
  `https://acme.example/tier = enterprise` added in 4 ops / 4 simulated ms;
  the secret read is logged redacted, never in plain text.
- Acme pre-token-issuance action: token **denied** — requested scope
  `admin:write` is not granted (fail-closed trigger).
- Globex slow action: 120-iteration loop **timed out at 101 ops** against
  the 100-op budget; post-login is fail-open, so the login still
  succeeded and the timeout was audited.
- Cross-tenant deploy refused (`action 'acme-post-login' not found for
  tenant 'globex'`) and cross-tenant access denied by permission check.
- Audit log: 3 entries, hash chain valid. Health check: ok, 2 tenants,
  3 actions.

## Test results

- **16 pytest tests, all passing** (`tests/test_runtime.py`).
- Covered: claim setting, deny, fail-closed denial on error, fail-open
  continuation, op-budget timeout, unknown-op rejection at registration,
  oversize-claim rejection, cross-tenant deploy refusal, secret
  redaction, per-tenant cache isolation, idempotent registration, audit
  chain verification + tamper detection, K8s manifest rendering, health,
  metrics/p95.

## How to run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_demo.py
```

## What the local runtime does and does not do

- Latency is **simulated** (1 ms charged per op) so results are
  deterministic; it is not a wall-clock measurement.
- Tenant code runs as validated step-plans in an interpreter, not as
  native Go/Node.js execution — the sandboxing model is the allow-list
  plus the op budget, not OS-level isolation.
- There is no real network, database, or Kubernetes cluster: the API
  layer is in-process, `call_api` hits an in-process endpoint registry,
  and the K8s manifests are generated YAML data.
- The TypeScript example is a fixture showing the authoring model; the
  runtime executes the equivalent restricted step-plan.
