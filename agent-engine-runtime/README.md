# Agent Engine Runtime

The core of an agent development platform, built for the **MongoDB —
Software Engineer 3, Atlas Agent Engine** role (REQ 4273615111): an agent
runtime with concurrent execution, session memory, a retrieval layer,
and an identity & governance layer — the runtime, memory, retrieval,
identity, and governance layers the JD names.

All data is synthetic and seeded. No network calls, no model calls, no
credentials. Standard library only, plus pytest for tests.

## What it does

- **Agent runtime** (`agent_engine/runtime.py`): steps run in order with
  shared context; a failing step retries with exponential backoff; a
  per-run step budget stops runaway agents; `run_many` runs several
  agents concurrently in a thread pool and returns results in task order.
- **Session memory** (`agent_engine/memory.py`): short-term working memory
  (capped, most-recent-first) plus long-term episodic memory. Recall ranks
  past turns by token overlap with a recency bonus — and never returns
  another tenant's episodes.
- **Retrieval layer** (`agent_engine/retrieval.py`): a deterministic
  token-overlap index over tools, knowledge docs, and runbooks, with a
  length penalty so a short on-topic document outranks a long loose one.
- **Identity & governance** (`agent_engine/governance.py`): tools are
  registered with required scopes (MCP/A2A style). A call is allowed only
  when the caller's tenant matches the resource tenant, the caller holds
  every required scope, and no deny policy matches. Deny-by-default: with
  no matching allow policy the call is denied. Every decision is written
  to an audit log.
- **Developer CLI + SDK** (`agent_engine/cli.py`, `agent_engine/sdk.py`):
  `Engine` wires the pieces together; the CLI lists tools/agents, runs an
  agent, recalls history, and searches the knowledge index.

## Run it

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python run_demo.py
python -m agent_engine.cli list-tools
python -m agent_engine.cli run demo --question "refund policy"
python -m agent_engine.cli search "refund policy"
```

## Test results

**25 passed, 0 failed** (goal venv Python 3.12, pytest 9.2.0).

Coverage: step order and shared context, retry-then-recover, give-up
after retries, step-budget exceeded, concurrent `run_many` (4 agents
finish faster than sequential), working-memory cap, episodic recall
ranking, cross-tenant recall isolation, retrieval ranking and kind
filter, deny-by-default, scope checks, deny-beats-allow, cross-tenant
denial, audit logging, end-to-end demo agent, and CLI commands.

## Honest limits

The demo agent, tools (calculator, echo), and knowledge docs are seeded
fixtures, not a production agent platform. The retrieval ranking is
token overlap, not embeddings or vector search. The runtime is threaded,
not distributed — it demonstrates the execution, budget, and retry
semantics, not a scaled-out service. Concurrency is verified at demo
scale (4 agents); timings are not production benchmarks.
