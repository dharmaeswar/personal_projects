# Rapid Prototype Workbench

An innovation-lab workbench: it takes an idea brief and turns it into a
working prototype across the full stack — JSON API, data pipeline, and a
frontend page a real user can open — then measures it with real user
feedback and decides iterate, pivot, or kill.

Built as the role project for the **Stripe — Software Engineer,
Experimental Projects** application (Greenhouse 8394936): an in-house
innovation lab that goes from concept to functional prototype in days,
builds across the stack, uses AI coding tools and agents, builds
products for AI and agent use cases, and validates with real users.

A NEW project: no existing subfolder in `dharmaeswar/personal_projects`
is an idea-to-prototype incubator. The closest projects cover different
problems — `agent-engine-runtime` runs agents (execution, memory,
retrieval, governance), `agentic-service-delivery-platform` rolls out
services to production, `python-backend-api-service` is one backend API
for a single checkout flow, and `realtime-event-intelligence-api` is a
single streaming backend. None takes an idea brief, scaffolds a
full-stack prototype (API + pipeline + frontend page), captures user
feedback, and decides iterate/pivot/kill — and none exposes the whole
loop as tools an AI agent can call.

All data is synthetic and seeded. No network calls, no model calls, no
credentials. Standard library only, plus pytest for tests.

## What it does

- **Idea briefs** (`prototype_lab/ideas.py`) — a brief needs a title, a
  problem, a target user, a hypothesis, and a success metric; empty
  fields and bad slugs are rejected, and duplicate slugs are refused.
- **Scaffolding** (`prototype_lab/scaffold.py`) — a brief becomes a
  prototype with the same full-stack shape every time: a JSON API
  (health, items, feedback), a four-stage data pipeline
  (ingest → validate → dedupe → aggregate), and a frontend page. A
  build longer than 5 days is rejected — a prototype that takes weeks
  is not a prototype. A live prototype blocks a second one per idea
  until it is retired.
- **Running service** (`prototype_lab/service.py`) — one small stdlib
  HTTP service serves the API and a plain HTML page per prototype
  where a user can try it and leave feedback.
- **Feedback pipeline** (`prototype_lab/pipeline.py`) — feedback events
  (user, prototype, rating 1–5, comment, day) are validated, deduped
  per user per day, and aggregated into count, average rating,
  promoter/detractor share, and per-day counts. Invalid events are
  quarantined with a reason, never silently dropped.
- **Decisions** (`prototype_lab/feedback.py`) — plain, arguable rules:
  under 10 responses is not enough data; avg ≥ 4.0 with ≥ 60%
  promoters means iterate; avg ≤ 2.5 means kill; anything in between
  means pivot — change one thing and re-test.
- **AI-agent tool surface** (`prototype_lab/agent_tools.py`) — a stdio
  JSON-RPC 2.0 server (MCP-style) exposing four tools an AI agent can
  call: `list_ideas`, `scaffold_prototype`, `submit_feedback`,
  `prototype_metrics`. It only runs these fixed handlers, so a tool
  call can never write arbitrary state or run arbitrary code.

## Run it

```bash
python3 run_demo.py            # seed 2 ideas, scaffold, feedback, decisions
python3 run_demo.py --port 8000  # also serve the API + prototype pages
python3 -m pytest tests -q     # 31 tests
```

## Results (seeded demo run)

- Feedback ingest: 24 accepted, 0 duplicates, 0 quarantined.
- `devtool-error-explainer-v1` (plain-language API error explainer):
  12 responses, avg rating 4.58, 100% promoters → **iterate**.
- `one-tap-tip-jar-v1` (one-tap $2 tip for creators): 12 responses,
  avg rating 3.17, 33% promoters → **pivot** (users want to pick the
  amount — change one thing and re-test).
- Live smoke test: `GET /api/health` → `{"status": "ok"}`;
  `GET /prototypes/devtool-error-explainer` renders the prototype page;
  `POST /api/feedback` round-trips and updates metrics.

## Honest limits

- A portfolio project on synthetic data, never presented as production
  or job experience. There is no Stripe, payments-transaction, or
  production-prototype work in the record, and the resume claims none.
- The service is single-process and in-memory: restarting it loses
  state. It is a prototype of a prototyping tool, not a hosted system.
- Feedback thresholds (10 responses, 4.0/2.5 ratings) are chosen
  defaults for a small test, not validated product-research constants.

## Layout

```
prototype_lab/
  ideas.py        idea briefs + registry
  scaffold.py     brief -> full-stack prototype
  service.py      HTTP API + frontend pages
  pipeline.py     feedback ingest -> metrics
  feedback.py     iterate / pivot / kill rules
  agent_tools.py  stdio JSON-RPC tool server for AI agents
run_demo.py       seeded end-to-end demo (+ optional server)
tests/
  test_prototype_lab.py   31 tests
```
