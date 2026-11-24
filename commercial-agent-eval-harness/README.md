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

## Results (seeded, reproducible)

- Eval suites: **9/9 cases pass** — invoice agent 5/5 (715 ms, $0.004800),
  support-triage agent 4/4 (670 ms, $0.004260).
- Regression vs baseline: **PASS** (pass rate 100% -> 100%, no regressions).
- Evidence evaluation: **clean draft 2/2 supported (groundedness 1.0)**;
  stale, unsupported and unknown-source drafts each score 0.0 with the
  right verdict; feedback loop re-ranks retrieval after one correction.
- Tests: **55 pytest tests, all passing** (41 original + 14 evidence).
- Edge cases covered: amount mismatch flagged, missing PO flagged, outage
  escalated to engineering without a KB lookup, refund escalated to billing,
  duplicate invoice/PO pair re-processed cleanly.

## Notes and limits

- **All data is synthetic.** Vendors, invoices, purchase orders, customers,
  tickets and knowledge-base articles are invented for this harness.
- **No real LLM or API calls.** The agents are deterministic policies and
  the latency/cost figures come from a fixed per-tool model in
  `agent_eval/tracer.py` — they are harness constants, not measured model
  pricing or production latency.
- The harness runs locally in plain Python (standard library + pytest).
