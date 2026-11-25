# AI SDLC Agent Platform

An agentic platform for the software development lifecycle — the kind of
thing a CrowdStrike AI SDLC Engineer builds: agents that carry well-scoped
work from code generation through review, testing and release, grounded in
a graph of the codebase, routed to the cheapest model that can do each job,
and graded by benchmarks on real-world tasks instead of by intuition.

## What it does

- **Agentic SDLC workflow** (`sdlc_agents/agents.py`) — four stage agents run
  in order over a ticket: CodeGen grounds the ticket in the context graph,
  reads the target file and emits a patch that must parse; Review fans out
  to one subagent per changed file and merges findings (blocking findings
  fail the stage); TestGen generates parameterized cases from the fix type
  and runs them against the patched function in an isolated namespace;
  Release is a gate — any failed gate blocks the release and names the
  reason. Every stage acts through the tool server, so every action is
  traced.
- **Graph-based context grounding** (`sdlc_agents/context_graph.py`) —
  a knowledge graph over files, functions, tests and tickets (defines /
  tested_by / fixes edges). `ground()` ranks nodes by token overlap plus a
  one-hop boost, so a matched function pulls in its file, tests and tickets.
  First-try hit rate on the seeded tickets is 1.0 — no multi-turn search.
- **MCP-style tool server** (`sdlc_agents/tools.py`) — tools declare JSON
  input schemas; calls are validated before dispatch and traced with
  latency and cost.
- **Model routing** (`sdlc_agents/routing.py`) — each task type has a
  capability floor (codegen 0.80, review 0.65, testgen 0.70, triage 0.50);
  the router picks the cheapest model that meets it, honours latency
  budgets, and records every decision in a spend ledger.
- **Benchmark suites** (`sdlc_agents/benchmarks.py`) — tasks graded on
  bug detection, review quality and latency against known expected answers;
  A/B comparison with per-kind deltas and a verdict; Pareto-frontier
  tracking over (cost, quality) points.
- **Observability** (`sdlc_agents/observability.py`) — every run lands in
  SQLite; the dashboard reports pass rate by stage, spend by model, blocked
  releases, and unreviewed auto-merges (0 by design — the release gate
  blocks auto-merge past a failed gate).

## Run it

```bash
pip install -r requirements.txt   # pytest only
python -m pytest -q               # 38 tests
python run_demo.py                # seeded run; writes sdlc_report.json + DASHBOARD.md
```

## Demo results

- 3 seeded tickets (off-by-one, bare except, missing validation): all four
  stages pass on every ticket; grounding first-try hit rate 1.0.
- 9 tool calls, 0 failed; model spend $11.30 across the run (ledger total).
- Benchmark suite (6 tasks): improved agent scores 1.0 mean, 1.0 pass rate;
  A/B vs a generic baseline: delta +0.667, verdict "candidate wins".
- Pareto frontier over (cost, quality): (0.02, 0.55), (0.10, 0.82), (0.35, 0.93).
- Dashboard: 12 stage runs, 100% pass rate, 0 blocked releases.

One real bug found and fixed by the tests: the codegen snippet for the
bare-except fix was an `except` clause with no `try`, so the generated patch
did not parse — the snippet is now a complete try/except block.

## Honest limits

All repo files, tickets and benchmark tasks are synthetic and seeded; no
real CrowdStrike code, model, or developer data is involved. The stage
agents are deterministic rule-based stand-ins, not live LLM calls — the
harness, tool schemas, grounding, routing and gates are the real platform,
and swapping in a coding-agent SDK means replacing the decision logic
inside each stage. The model capability/cost/latency table is illustrative,
not measured on any real model. The "API" is in-process, the store is
SQLite, and the demo runs 3 tickets, not production scale. Not implemented:
a live LLM call, real Kubernetes deployment, real event-pipeline
instrumentation at CrowdStrike scale, or a production benchmark program.
