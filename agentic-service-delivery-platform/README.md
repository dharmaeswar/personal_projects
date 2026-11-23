# Agentic Service-Delivery Platform

A portfolio project for a platform / full-stack software-engineering role
(Apple's Forge / Enterprise Technology Services style). It models the
platform side of shipping software: instead of checking one release, it
takes a service from code to production through an agent-driven rollout.

**All data is synthetic and local.** No real services, deployments, or
production traffic are involved, and nothing here is a claim about any
real company's systems.

## What it does

- **Service registry** (`delivery_platform/services.py`) — services declare
  how they want to deploy: health checks, CPU/memory limits, canary
  stages, rollback plan, on-call owners, and a deploy window.
- **Deployment guardrails** (`delivery_platform/policies.py`) — six shared
  guardrails run over every template before any traffic moves: health
  checks present, resources inside platform caps (4 cores, 8192 MB),
  canary stages starting at 5% or less and ending at 100%, a rollback
  plan with a version, steps, and auto-rollback, a primary on-call owner
  plus a different backup, and a valid deploy window.
- **Agentic rollout workflow** (`delivery_platform/agent.py`) — the agent
  plans a six-step rollout (validate, canary 5/25/50%, full rollout,
  verify SLOs). Low-risk steps auto-approve; medium- and high-risk steps
  need an explicit human approval, and a missing approval counts as a
  denial. A denied step stops the rollout and triggers an automatic
  rollback. Every decision lands in an append-only audit log with actor,
  timestamp, and reason, so any rollout can be replayed end to end.
- **SLI/SLO tracking** (`delivery_platform/slo.py`) — availability, latency
  p95, remaining error budget, and error-budget burn rate against a
  target, with plain-language alerts when a service breaches its SLO.
- **Agent-queryable data interface** (`delivery_platform/data_interface.py`)
  — a read-only query surface with a published schema (`query_service`,
  `list_services`, `get_slo_summary`, `list_audit`). Agents can read
  everything they need to plan a rollout, and cannot mutate platform
  state through it: the platform's data is AI-ready by design.
- **Managed operations** (`delivery_platform/ops.py`) — the operations
  side of the platform: per-region health scoring from availability,
  automation coverage, and open incidents; manual vs automated toil
  tracking; and an agentic-first incident-response agent. The ops agent
  proposes a remediation per severity (sev1 failover, sev2 restart,
  sev3 cache clear); low-risk actions auto-approve, high-risk actions
  need an explicit human approval, and a denied action escalates to
  on-call instead of running. Every decision is audited, and every
  automated action records the manual toil minutes it saved.

## Results (seeded, reproducible)

- Rollout demo: critical checkout API goes live through 6 steps with
  human approvals; the non-compliant billing worker is blocked by
  guardrails before any traffic moves.
- SLO demo: checkout-api 200 samples, availability 0.9950, burn rate
  5.0x, latency p95 58.0 ms.
- Managed-operations demo: 2 regions, 40.0 manual vs 80.0 automated
  toil hours/week (66.7% automation coverage); health us-west-2 84.5/100,
  us-east-1 80.0/100; sev2 incident mitigated by an auto-approved restart
  (25 toil minutes saved); sev1 failover denied without approval and
  escalated.
- Tests: **48 pytest tests, all passing** (36 rollout/guardrail/SLO/
  interface tests + 12 managed-operations tests).

## How it differs from the other projects in this repo

- `deployment-guardrails-platform` validates deployment *templates* for a
  fleet; this project runs the *rollout itself* — an agent plans steps,
  waits on human approvals, rolls back on denial, and audits each
  decision.
- `agentic-analytics-statistical-evaluator` and
  `commercial-agent-eval-harness` evaluate LLM/agent *outputs*; this
  project puts an agent *in the loop of a production workflow* with
  guardrails, approvals, and SLO verification.

## Run it

```bash
python -m pytest -q
python run_platform.py
```

The demo registers three services (one deliberately fails guardrails),
rolls out the critical checkout API with human approvals, records
synthetic SLO samples, runs the managed-operations demo (region health,
toil report, and two incidents), and writes `platform_report.txt`.

## Requirements

Python 3.10+, standard library only. Tests need `pytest`.
