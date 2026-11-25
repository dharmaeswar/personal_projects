# Commercial Agent Eval Harness

An evaluation harness for commercial multi-agent business workflows — the
kind of thing an Applied AI Engineer builds for customers: eval suites that
act as the customer's **acceptance criteria**, an MCP-style tool server for
the business systems the agents call, full tool-call tracing with latency
and cost tracking, and a pass/fail regression check against a baseline.

Two agents run over synthetic business data:

- **Invoice agent** (finance ops): validates an invoice against its
  purchase order and approves it only when vendor, amount and PO status all
  match; otherwise it flags the invoice with a reason.
- **Support-triage agent**: classifies a support ticket, searches the
  knowledge base, resolves it when an article answers the question, and
  escalates outages to engineering and refunds to billing.

## What it does

- **MCP-style tool server** (`agent_eval/tools.py`): 9 tools with JSON
  input schemas (`lookup_invoice`, `lookup_po`, `approve_invoice`,
  `flag_invoice`, `lookup_customer`, `get_ticket`, `search_kb`,
  `resolve_ticket`, `escalate_ticket`). Arguments are validated against
  the schema before dispatch, and every call is traced.
- **Multi-agent workflows** (`agent_eval/agents.py`): the two agents above.
  They are deterministic rule-based policies — stand-ins for LLM agents —
  so every eval is reproducible with no model API calls. Swapping in a
  real Claude Agent SDK agent means replacing the decision logic; the
  tools, tracer and evals stay the same.
- **Tool-call tracing** (`agent_eval/tracer.py`): every call records tool,
  arguments, simulated latency and cost, and outcome. Totals are reported
  per case and per suite.
- **Eval suites as acceptance criteria** (`agent_eval/evals.py`): 9 cases.
  A case passes only when the decision matches, every required tool was
  called, no unexpected tool errored, and the latency/cost budgets hold.
- **Regression vs baseline** (`agent_eval/regression.py`): compares a fresh
  run with `baseline.json` per case — a newly failing case, a missing case,
  or latency/cost growth over 10% is a REGRESSION.
- **Reports** (`agent_eval/report.py`): JSON + plain-text summaries.

## Run

```bash
pip install -r requirements.txt
python run_evaluation.py            # compare with baseline.json
python run_evaluation.py --record-baseline   # overwrite baseline.json
python run_evidence_eval.py         # evidence-grounded draft evaluation
python -m pytest -q
```

## Evidence-grounded draft evaluation (added Nov 24, 2026)

`agent_eval/evidence.py` adds the layer an AI content platform needs on
top of agent evals: every claim in a generated draft must trace to an
approved source **and** to the version current when the draft was made.

- **Evidence store** — versioned approved content, append-only versions,
  per-source access roles (a drafter cannot cite a reviewer-only source).
  Retrieval returns the source id and current version with every result.
- **Draft evaluator** — one verdict per claim: `supported`,
  `unsupported` (claim words no approved source contains), `stale-version`
  (cited a superseded version), `unknown-source`, or `access-denied`;
  plus a groundedness rate across the draft.
- **Review-feedback loop** — a reviewer correction records an approval
  boost for the corrected source, so later retrieval ranks
  reviewer-approved sources first for that brand.

Run it with `python run_evidence_eval.py` (writes `evidence_report.json`).

## AI spend management backend (added Nov 25, 2026)

`agent_eval/spend.py` adds the backend an AI spend-management product
needs on top of agent evals: every agent run costs tokens and dollars,
and a finance team needs to see who spent what, on which model, against
which budget — before the bill lands.

- **Spend ingestion** — schema-validated events (`team`, `model`, `agent`,
  prompt/completion tokens, day); cost is priced from a fixed per-model
  table when the event does not carry its own cost. Bad events (unknown
  model, negative tokens, bad date) are rejected, never silently stored.
- **Aggregation** — totals plus per-team, per-model and per-day breakdowns
  (`SpendLedger.summary`), and monthly spend per team/model.
- **Budgets and alerts** — monthly USD caps per team (optionally per
  model) with warn (80%) and breach (100%) thresholds, a forecast alert
  when the run rate projects past the cap by month end (needs 3+ days of
  data), and a daily-spike alert when one day costs over 2x the daily mean.
- **Tracer feed** — `ledger.from_tracer(tracer, team, model)` turns a
  finished eval run's traced tool calls into spend events, so eval cost
  and product spend are measured from the same source.

Run it with `python run_spend.py` (writes `spend_report.json`).

## Cash Equities client targeting + RAG evaluation (added Nov 25, 2026)

`agent_eval/rag_targeting.py` extends the harness for Cash Equities
Sales analytics: a deterministic "who to call" ranker over synthetic
client-flow data (trades, axes, IOIs, trade-idea fit, near-term
catalysts) with a plain-language rationale per client, and a RAG judge
that scores LLM-generated client content claim by claim against
retrieved sources — supported / unsupported / missing source — plus a
prompt-variant comparison by groundedness.

- **Ranker** (`score_client`, `rank_clients`): weighted score — flow
  35%, axes+IOI liquidity 25%, trade-idea match 25%, catalyst 15%.
- **RAG judge** (`evaluate_draft`): a claim is supported only when
  every keyword appears in the cited source; anything else is flagged
  as hallucinated.
- **Prompt comparison** (`compare_prompt_variants`): grounded prompt
  1.00 groundedness vs loose prompt 0.75 — the loose draft's extra
  claim ("$90m in technology") is correctly flagged unsupported.

Run it with `python run_cash_equities_eval.py` (writes
`cash_equities_eval_report.json`). On the seeded data the verdict is
**PASS**: top client Beacon Hill Capital scores 71.7; 86 pytest tests
pass (70 original + 16 new).

## Results (seeded, reproducible)

- Eval suites: **9/9 cases pass** — invoice agent 5/5 (715 ms, $0.004800),
  support-triage agent 4/4 (670 ms, $0.004260).
- Regression vs baseline: **PASS** (pass rate 100% -> 100%, no regressions).
- Evidence evaluation: **clean draft 2/2 supported (groundedness 1.0)**;
  stale, unsupported and unknown-source drafts each score 0.0 with the
  right verdict; feedback loop re-ranks retrieval after one correction.
- Spend demo: **36 events, 553,020 tokens, $2.1957** across 2 teams and
  3 models; finance breaches its $0.50 budget ($2.15, driven by the
  $2.10 spike day), support is forecast to $0.30 vs a $0.20 budget, and
  the finance spike day is flagged at 234.4x the daily mean.
- Tests: **104 pytest tests, all passing** (70 original + 16 Cash Equities targeting/RAG + 18 change-gate).
- Change-gate demo: **1/5 sample changes pass** — the clean agent change
  scores 100; the other four each fail a different stage (syntax error,
  `eval` + hardcoded password, triple-nested loop in a hot path, failing
  tests with no retrieval context).
- Edge cases covered: amount mismatch flagged, missing PO flagged, outage
  escalated to engineering without a KB lookup, refund escalated to billing,
  duplicate invoice/PO pair re-processed cleanly.

## AI-generated-code change gate (added Nov 25, 2026)

`agent_eval/change_gate.py` adds the compile/test/evaluate pipeline an
Agentic AI team runs before an agent's change can ship:

- **Compile gate** — real Python `compile()` on every changed file.
- **Static analysis** — unused imports and over-long functions via `ast`.
- **Style checks** — line length, trailing whitespace, tab indentation.
- **Safety checks** — banned calls (`eval`, `exec`, `os.system`,
  `pickle.loads`), `shell=True`, hardcoded credentials/secrets.
- **Performance gates** — added-line budgets and a loop-depth budget for
  files flagged as hot paths.
- **Tests** — the change must claim a test run, and all claimed tests
  must pass.
- **Retrieval-context coverage** — every changed file must be covered by
  a snippet from the context the agent was given, so the change is
  auditable against what the agent actually read.
- **Code-review score** — 100 minus a fixed deduction per failed stage;
  a change passes only with no failed stage and a score of 70+.

Run it with `python run_change_gate_eval.py` (writes
`change_gate_report.json`; exits non-zero when any sample change fails,
which is the gate working — 4 of the 5 seeded samples are meant to
fail). Retrieval context itself comes from the existing evidence store
(`agent_eval/evidence.py`) and the RAG targeting module
(`agent_eval/rag_targeting.py`) — no separate retrieval module was
needed.

## Notes and limits

- **All data is synthetic.** Vendors, invoices, purchase orders, customers,
  tickets and knowledge-base articles are invented for this harness, as
  are the Cash Equities clients, flows, axes and IOIs in the targeting
  module — no real clients or trading data.
- **No real LLM or API calls.** The agents are deterministic policies and
  the latency/cost figures come from a fixed per-tool model in
  `agent_eval/tracer.py` — they are harness constants, not measured model
  pricing or production latency.
- The harness runs locally in plain Python (standard library + pytest).
