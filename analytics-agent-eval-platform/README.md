# Analytics Agent Eval Platform

An analytics agent plus the evaluation infrastructure that keeps it honest
— the kind of system Reddit's Data Science Platform team builds around
Rosso, its analytics agent: multi-step agent workflows over data, evals
that decide what ships, and sandboxed execution with provenance so every
answer can be reproduced.

Built for the Reddit — Senior Software Engineer, AI & Science Platform
application (Greenhouse job 8411613). All data is synthetic and seeded;
nothing here is real Reddit data, users, or communities.

## The problem

An analytics agent that answers data questions is only useful if its
answers are right, its failures are visible, and its execution is safe.
Three things go wrong without that layer: the agent states a number it
never computed, a bad query runs away with the warehouse, and nobody can
tell whether a new model version is better or worse than the last one.
This project is that layer: a tool-using agent, a sandboxed runner, and
an eval harness with versioned task sets, regression reports and release
gates.

## What it does

- **Agent workflow** (`agent_eval/agent.py`) — five explicit steps per
  question: retrieve dataset context, translate to SQL, execute in the
  sandbox, validate the result, summarize from the returned rows only.
  Execution state is explicit (complete / incomplete); one repair retry,
  then the task is marked incomplete with the reason — never answered
  from invented data.
- **MCP-style tool server** (`agent_eval/tools.py`) — five tools with JSON
  input schemas (`describe_dataset`, `text_to_sql`, `run_query`,
  `validate_result`, `summarize`). Arguments are validated before
  dispatch; every call is traced with latency and simulated cost, the
  way a model gateway would meter tool use.
- **Text-to-SQL** (`agent_eval/text_to_sql.py`) — a deterministic
  pattern-based translator, a stand-in for a text-to-SQL model so evals
  are reproducible with no model API calls. It raises a clear error
  outside its supported patterns instead of guessing SQL.
- **Sandboxed execution** (`agent_eval/sandbox.py`) — SELECT-only,
  single-statement queries over seeded SQLite tables (`communities`,
  `posts`); per-role table allow-lists, row and time limits, and a full
  audit trail (query hash, dataset version, role, rows, latency) so any
  result can be reproduced from its provenance.
- **Eval harness** (`agent_eval/evals.py`) — versioned task set v1: 8
  scored cases (ranking, aggregation, time-series) with reference SQL, 6
  human-reviewed, plus a failure-handling case (unknown community) the
  agent must decline to answer. Graders check exact results and summary
  groundedness; their limitations are documented in the module.
- **Regression + release gates** (`agent_eval/regression.py`) — a fresh
  run is compared with `baseline.json`: a newly failing case, a missing
  case, or latency/cost growth over 10% is a REGRESSION. The gate blocks
  rollout when the pass rate falls below 0.875, a human-reviewed case
  fails, or the failure-handling case stops declining.
- **Audit + reproducible artifacts** (`agent_eval/provenance.py`) — every
  run writes a run record (run id, dataset version, SQL hash, tool
  trace) and a plain-text regression report.

## Run it

```bash
pip install -r requirements.txt
python run_demo.py     # prints the eval report, writes eval_report.json/.txt and baseline.json
python -m pytest -q    # 34 tests
```

## Demo results

- Eval set v1: **8/8 passed (100%)**, release gate **PASS**.
- Failure handling: **PASS** — the unknown-community question was
  reported incomplete ("no known community in question") instead of
  being answered from invented data.
- All 8 summaries grounded: every number in each summary appears in its
  result rows. Audit trail: 16 entries (8 reference queries + 8 agent
  queries).

## Honest limits

- The text-to-SQL translator is deterministic pattern matching, not a
  model; the eval harness measures the agent workflow around it, not
  text-to-SQL quality. No LLM calls, model gateway, or retrieval system
  is implemented; tool costs/latencies are illustrative metering
  constants, not measured.
- The sandbox is single-process SQLite over ~400 seeded posts, not
  BigQuery/Trino/Spark/Airflow at production scale. The agent has no
  real auth integration, no staged rollout, and no incident-response
  path — those are named as the production gaps in the role notes.
- The exact-result grader fails on ties unless the reference SQL pins
  the tie-break, and the groundedness grader cannot judge whether a
  summary states the right conclusion from correct numbers.
