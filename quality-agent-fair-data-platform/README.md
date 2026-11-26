# Quality Agent FAIR Data Platform

An agentic Quality-analytics workflow over FAIR data products, with an
MCP server connecting the agents to enterprise data and an evaluation /
monitoring layer that keeps the agents honest.

Built as the role project for Amgen — Senior Data Scientist, Global
Quality Analytics & Innovation (GQAI), Req R-262535. **All data is
synthetic and seeded in code.** No real Amgen, company, or production
data appears anywhere, and nothing here ran in production or at any real
company. No production AI-agent deployment is claimed — this is a local,
deterministic portfolio project.

## The problem

A Quality team wants AI agents that answer questions like "why did batch
release cycle time rise?" — but an agent that guesses a number is worse
than no agent. Three things have to exist first:

1. **FAIR data products** — the agent's evidence must be findable,
   governed, versioned and reusable, not raw feeds.
2. **An MCP server** — the agent reaches enterprise data only through
   typed tools with validated arguments, never by free-form access.
3. **Evaluation and monitoring** — every number in an answer is
   recomputed from the tool results before it ships, and run-over-run
   health is watched for drift.

This project is that stack, end to end, over seeded Quality data
(batch releases, deviations, CAPAs).

## What it does

| Module | What it covers |
|---|---|
| `quality_platform/fair.py` | FAIR data-product registry: registration with validation, ranked search (name matches weigh double), freshness-SLA status, role-based governed access, lineage, product cards. Draft/deprecated products never surface in search. |
| `quality_platform/mcp.py` | JSON-RPC 2.0 MCP server (`initialize`, `tools/list`, `tools/call`, `ping`) with five tools: `search_data_products`, `get_product_metadata`, `run_quality_check`, `get_quality_metrics`, `list_lineage`. Arguments are validated against each tool's JSON schema; failures are structured errors. A thin `MCPClient` wraps it. |
| `quality_platform/agents.py` | Agentic workflow — Planner, Retriever, Analyst, Validator. The Planner turns a question into MCP tool steps; the Retriever runs them; the Analyst composes an answer strictly from tool results; the Validator recomputes every number in the answer and flags any unverified one. Missing data means the agent declines instead of guessing. |
| `quality_platform/evaluate.py` | Eval harness: a rubric judge scores each trajectory on grounding, tool use, numeric accuracy and coherence, with hard fails for hallucinated numbers and errored tool calls; a monitor alerts when pass rate falls below 0.8 or latency grows over 10% run over run. |
| `quality_platform/seed.py` | Seeded synthetic data: 12 batch records, 10 deviations, 3 CAPAs, and three FAIR products (batch-release, deviation-register, capa-tracker). |
| `quality_platform/pipeline.py` | One-call end-to-end run: investigation + eval suite + monitor report. |

## Run it

```bash
pip install -r requirements.txt   # pytest only; app code is stdlib-only
python run_demo.py                # one investigation + eval summary
python run_evaluation.py          # the 6-case eval suite
python -m pytest -q               # 42 tests
```

## Demo results (real run, seeded data)

- Question: "Why did batch release cycle time rise from Q2 to Q3?"
- Answer: mean batch release cycle time rose from **20.0 days in Q2 to
  27.5 days in Q3, a change of 7.5 days**, across 6 batches per quarter.
  Deviations total **10**, led by **documentation (7 reports)**.
  The batch-release data passed its quality checks.
- Validator: every number in the answer recomputed from tool results —
  **0 unverified numbers**, investigation passed.
- Evals: **6/6 cases passed** (judge mean 1.0); monitor: no alert.

## Honesty notes

- The agents are deterministic policies over seeded data, not a live LLM
  — the same interfaces a real LLM agent would plug into.
- MCP here is the JSON-RPC tool protocol shape, implemented in-process;
  it is not a connection to any live enterprise system.
- Quality scores, cycle times and deviation counts are invented seed
  values used to exercise the pipeline, not measurements of any real
  process.
