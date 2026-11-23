# Agentic DevOps Access Gateway

An RBAC-secured remote-server gateway that connects DevOps agents to
customer environments — the access-control layer in front of the
remote servers an agentic DevOps system reaches into. An agent can only
act through a short-lived, narrowly scoped capability token, and every
action passes four gates (token, scope, role policy, server health)
before it runs. Every outcome, allowed or denied, lands in an
append-only audit log.

Built as a portfolio project for an Amazon Software Dev Engineer, AWS
Agentic AI DevOps application (auth/RBAC, remote servers, LLM/agentic
backends, distributed systems). All data is synthetic and local; nothing
here describes a real AWS system, real customer, or real environment.

## What it does

- **Scoped capability tokens** (`gateway/tokens.py`) — HMAC-SHA256
  signed tokens binding an agent to a role, a narrow scope list
  (`action:resource`), one environment, and an expiry time. Tokens are
  verified on signature, expiry, and revocation; only a hash is stored.
- **Policy engine** (`gateway/policy.py`) — role → allowed
  action/resource pairs with glob patterns, default-deny. A deployer can
  deploy, an operator can only restart web services, a reviewer can only
  read and approve, and only admin can do anything.
- **Remote-server registry** (`gateway/registry.py`) — servers register
  with environment and endpoint; heartbeats keep them healthy and stale
  servers (no heartbeat for 5 minutes) go unhealthy and are refused.
- **Audit log** (`gateway/audit.py`) — append-only, immutable entries
  for every action with actor, action, resource, server, decision, and
  reason, so any agent session can be replayed end to end.
- **Gateway** (`gateway/gateway.py`) — runs the four gates in order and
  makes retries idempotent: a repeated idempotency key returns the
  original result without re-executing the action.
- **HTTP surface** (`gateway/api.py`) — stdlib-only service:
  `GET /health`, `GET /v1/servers`, `GET /v1/audit`,
  `POST /v1/execute` (Bearer token, idempotency key supported).

## How it differs from the sibling projects in this repo

- `agent-security-validation-suite` is an **adversarial eval harness**:
  it tests whether an agent's guardrails and MCP authorization hold up
  against prompt injection and tool abuse, using fixed attack cases and
  scoring. This project is the **enforcement gateway itself**: it issues
  real scoped tokens and actually allows or denies live agent actions
  against remote servers, with revocation and health gating.
- `agentic-service-delivery-platform` runs an **agent-driven rollout
  workflow** (plan steps, human approvals, rollback, SLO verification)
  for services being shipped. This project controls **agent access to
  customer environments** — who may act, on what resource, in which
  environment — before any work happens, and audits each decision.
- `model-api-gateway` is an **API-key gateway for hosted model
  endpoints** (rate limiting, routing across model backends, token
  metering and billing). This project has no model serving, rate limits,
  or billing: its problem is least-privilege agent access to remote
  DevOps servers, with role policies, environment scoping, health
  checks, and idempotent retries.

## Run it

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python run_gateway.py
python -m pytest tests/ -q
```

The demo registers a prod and a staging server, issues deployer and
operator tokens, shows an allowed deploy, an idempotent replay, a
scope denial, and an environment denial, then prints the audit log.

## Results

- Tests: **44 pytest tests, all passing** — token issue/verify/expiry/
  revocation/tampering, policy allow/deny per role, registry health and
  staleness, audit completeness and immutability, gateway allow/deny for
  each gate, idempotent retries, and the HTTP endpoints (200/401/403).
- Demo: 1 action executed, 1 replay returned without re-executing,
  2 denials, 3 audit entries.

## Notes and limits

- **All data is synthetic.** Agents, servers, endpoints, and tokens are
  invented for this demo; no real customer environment is involved.
- The "execution" step is a simulated action record, not a real remote
  command: the gateway proves the access decision, not the remote call.
- Tokens are HMAC-signed with a server-side secret; in production the
  secret would live in a vault (e.g. AWS Secrets Manager), not in code.
