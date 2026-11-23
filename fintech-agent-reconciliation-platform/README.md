# Fintech Agent Reconciliation Platform

MCP-server-shaped finance agents in the shape of the Twitch SWE II,
Fintech role: Bedrock-style agents that automate Finance work —
reconciliations, reporting, variance analysis, and payouts — behind MCP
servers with OAuth 2.0 / OIDC scopes, guardrails, human-in-the-loop
approvals, evaluation, and auditability, on AWS-native infrastructure.

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
- `fintech_agents/observability.py` — metrics + hash-chained audit log
- `run_fintech.py` — end-to-end demo
- `tests/` — pytest suites for the ledger, MCP server, and agent

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_fintech.py
```

Demo output: 3/4 ledger entries matched (1 break), variance flagged at
+12.5%, a $50 payout executed, a $25,000 payout held for approval then
approved and executed, audit chain valid, eval 2/2 golden cases passed.
All data is synthetic and local; nothing here claims production use.
