# Fintech Agent Reconciliation Platform

MCP-server-shaped finance agents in the shape of the Twitch SWE II,
Fintech role: Bedrock-style agents that automate Finance work —
reconciliations, reporting, variance analysis, and payouts — behind MCP
servers with OAuth 2.0 / OIDC scopes, guardrails, human-in-the-loop
approvals, evaluation, and auditability, on AWS-native infrastructure.

## Finance AI layer (added Nov 2026 for the Veeam Finance AI Engineer role)

A Finance Transformation Office layer on top of the same platform:
a close agent that runs a month-end close cycle end to end — fetch
invoices from Finance systems, consolidate entities, reconcile the
ledger, compute ARR / billings / forecast variance, work a close
checklist, and evaluate the close report against golden cases before
marking the close ready — with the production shapes the role names:

- **Close, consolidation, ARR, billings** (`finance_close.py`):
  dependency-ordered close checklist, multi-entity consolidation
  with FX conversion, ARR roll-forward with net revenue retention,
  billings vs revenue (deferred-revenue change), forecast variance
  with a flag threshold.
- **Advanced SQL** (`finance_sql.py`): real SQLite queries using
  CTEs, window functions (running totals, LAG growth, RANK) and
  complex joins over revenue, billings and close data — the same
  shapes a Databricks SQL warehouse would run.
- **Databricks-shaped jobs** (`databricks_jobs.py`): jobs as task
  DAGs with retries on transient failures, data-quality checks
  (row-count floors, null-rate ceilings, freshness limits), and a
  run history. No live Databricks connection.
- **REST APIs + OAuth** (`finance_api.py`): a client with token
  fetch/refresh, cursor pagination, 429 back-off honouring
  Retry-After, and idempotency keys, against a fake in-memory ERP
  transport. No real API is called.
- **AI evaluation framework** (`eval_framework.py`): golden
  datasets, a deterministic rubric judge (accuracy, grounding,
  completeness), ungrounded-number detection, and a regression gate
  that fails a run when any score drops below its baseline.
- **Observability** (`observability.py`): structured JSON logging
  with trace/span ids, tracing (spans with durations), and AI cost
  tracking (tokens × stated price per 1k).
- **Close agent** (`close_agent.py`): multi-step orchestration with
  a traced step list, human approval for journal entries above
  $10,000, and a close that is only "ready" when the golden-case
  evaluation passes.

## What it models (from the Twitch Fintech posting)

- **Agentic AI systems**: an agent plans Finance workflows and calls
  tools through an MCP server — reconcile, variance report, payout
  create — with Bedrock-style orchestration (plan, call, check, act).
- **MCP servers**: a tool registry with per-tool OAuth 2.0 scopes
  (`finance:read`, `finance:payout`, `finance:approve`); unknown tools
  and missing scopes are denied, and arguments are guardrail-scanned
  (payout amount limits, PII redaction).
- **Finance workflows**: ledger-to-bank reconciliation (exact,
  amount+date, reference matching; breaks reported), variance analysis
  vs budget with flag thresholds, and idempotent payouts — replays
  never pay twice, and payouts above $10,000 wait for human approval.
- **Safety and trust**: guardrails on every tool call, human-in-the-loop
  approvals, golden-case evaluation (hallucination check: reported
  numbers come from the reconciler, never guessed), and a hash-chained
  audit trail.
- **AWS-native shape**: Lambda-shaped handlers, DynamoDB-shaped stores,
  SQS-shaped queues in the sibling platform modules; CloudWatch-shaped
  metrics (counters, p95 latencies) here.

## Layout

- `fintech_agents/ledger.py` — ledger entries, bank lines, reconciler, variance
- `fintech_agents/mcp.py` — MCP server: tools, OAuth 2.0 scopes, guardrails
- `fintech_agents/agent.py` — FinanceAgent: workflows, approvals, evaluation
- `fintech_agents/observability.py` — metrics + hash-chained audit log; structured logging, tracing, AI cost tracking
- `fintech_agents/finance_close.py` — close checklist, consolidation, ARR, billings, forecast variance
- `fintech_agents/finance_sql.py` — advanced SQL (CTEs, window functions, complex joins) over SQLite
- `fintech_agents/databricks_jobs.py` — Databricks-shaped jobs, retries, data-quality checks, run history
- `fintech_agents/finance_api.py` — REST + OAuth client (pagination, 429 backoff, idempotency) over a fake ERP
- `fintech_agents/eval_framework.py` — golden datasets, rubric judge, grounding checks, regression gate
- `fintech_agents/close_agent.py` — CloseAgent: traced multi-step close cycle with journal approvals
- `run_fintech.py` — end-to-end demo
- `run_close_demo.py` — Finance AI close-cycle demo
- `tests/` — pytest suites for the ledger, MCP server, agent, close, SQL, Databricks jobs, API, eval, and observability

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_fintech.py
python run_close_demo.py
```

Demo output: 3/4 ledger entries matched (1 break), variance flagged at
+12.5%, a $50 payout executed, a $25,000 payout held for approval then
approved and executed, audit chain valid, eval 2/2 golden cases passed.
Close demo: 5 invoices fetched, consolidation $84,300.00, ARR ending
$115,000.00 at 100.0% NRR, forecast variance +2.0% (not flagged),
checklist 100% done, eval 1/1 golden cases passed, close ready, AI
cost $0.005. All data is synthetic and local; nothing here claims
production use, a real ERP/Databricks connection, or a real model call.
