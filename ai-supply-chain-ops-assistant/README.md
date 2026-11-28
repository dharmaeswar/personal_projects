# AI Supply Chain Ops Assistant

An AI-powered operations assistant for a retailer's supply-chain team — the
kind of product Chewy's AI Supply Chain Operations team builds: it helps
employees find information, explore data, and complete tasks while remaining
in control.

Built as the role project for the **Chewy — Software Engineer I, AI Supply
Chain Operations** application (Req R30985-1, Bellevue, WA).

**Demo project. Synthetic data only.** No real Chewy system, warehouse,
order, or employee data is involved. All SKUs, runbooks, inventory numbers,
and eval tasks are seeded demo data. No network calls and no real model
calls: retrieval, analytics, and evaluation are deterministic local code
standing in for the AI services the real product would integrate, so every
behaviour can be tested end to end.

## The problem

Supply-chain operators answer the same questions all day — "why is this SKU
short?", "what is the reorder rule for this warehouse?", "which orders are
at risk from this carrier delay?" — by digging through runbooks, spreadsheets,
and dashboards. An AI assistant can answer from the team's own knowledge and
data, draft the follow-up workflow, and show its sources — but only if it
stays grounded, only acts with a human's approval, and gets evaluated on
representative tasks so bad answers are caught before operators trust them.

## What it does

- **Knowledge discovery** (`ai_ops/knowledge.py`) — retrieval over seeded
  operations runbooks (receiving, stockouts, reorder rules, carrier delays,
  returns). Token-overlap ranking with a stopword list; answers cite the
  runbook passage they came from, and abstain with a plain "I don't know"
  when nothing matches well enough — the honest behaviour for an AI
  assistant, not a confident guess.
- **Analytics** (`ai_ops/analytics.py`) — seeded inventory data (SKUs,
  warehouses, demand, on-hand stock). Answers data questions with recomputed
  numbers: fill rate, stockout SKUs, days of cover, slow movers, and
  at-risk orders for a carrier delay. Every answer carries the method used,
  so an operator can check it.
- **Workflow automation** (`ai_ops/workflows.py`) — drafts follow-up tasks
  from analytics signals (reorder, expedite, transfer). A task is only a
  draft until a human approves it; approval and rejection are recorded in an
  audit log, and repeating a request with the same idempotency key returns
  the original task instead of creating a duplicate.
- **AI evaluation** (`ai_ops/evaluate.py`) — an eval harness over
  representative tasks: runbook Q&A, analytics Q&A, and workflow drafts.
  Each candidate answer is checked for grounding (cites a real passage),
  numeric accuracy (recomputed from the data), and safe abstention when the
  question is unanswerable. Per-task pass/fail plus a summary report, so
  inaccurate or unexpected results are visible and fixable.
- **Service + UI** (`ai_ops/service.py`) — a standard-library HTTP API
  (`/ask`, `/workflows`, `/eval`, `/health`) and a small browser dashboard
  at `/` that calls the API: ask a question, see sources, draft and approve
  a workflow task, and run the eval suite.

## Run it

```bash
python3 run_demo.py        # knowledge + analytics + workflow + eval, printed
python3 run_service.py     # serves the API + dashboard on http://localhost:8080
python3 -m pytest tests/ -q
```

## Layout

```
ai_ops/
  knowledge.py    runbook store + retrieval + grounded answers
  analytics.py    seeded inventory data + computed answers
  workflows.py    draft/approve/reject tasks + audit log + idempotency
  evaluate.py     representative-task eval harness
  service.py      stdlib HTTP API + dashboard
tests/            pytest suite covering every module
run_demo.py       end-to-end demo
run_service.py    serves the API + dashboard
```

## Honest limits

- Retrieval is keyword overlap, not a real language model or embedding
  search; the design (cite sources, abstain when unsure, human review
  before action) is what transfers to the real product.
- The seeded data is synthetic; fill rates and stockouts are demo numbers.
- No live cloud, CI/CD, or monitoring is claimed — the code is structured
  so those layers can be added without changing the core logic.
