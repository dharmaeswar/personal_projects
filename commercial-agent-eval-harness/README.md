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
python -m pytest -q
```

## Results (seeded, reproducible)

- Eval suites: **9/9 cases pass** — invoice agent 5/5 (715 ms, $0.004800),
  support-triage agent 4/4 (670 ms, $0.004260).
- Regression vs baseline: **PASS** (pass rate 100% -> 100%, no regressions).
- Tests: **41 pytest tests, all passing**.
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
