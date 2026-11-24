# Enterprise AI Deployment Accelerator

Take a mid-market enterprise AI use case from prototype to a production
deployment — the work an Applied AI Engineer does with customers: pick
the right use case, build a retrieval-backed agent over the customer's
own documents, evaluate it systematically, gate the launch on real
evidence, and leave behind a reusable deployment playbook.

All data is synthetic and local. No real LLM or API calls: the agent is
a deterministic rule-based policy over a small document store, so every
eval is reproducible offline. A real model-backed agent plugs into the
same `plan / retrieve / answer / validate` interfaces.

## What it does

- **Use-case intake** (`enterprise_ai_deployment/intake.py`) — score
  candidate use cases on business value, data readiness and risk, then
  rank them so the team prototypes the highest-value, lowest-risk case
  first and defers the rest.
- **Retrieval** (`retrieval.py`) — in-memory document store with
  keyword retrieval; every hit carries its document id so answers can
  cite exactly what they used.
- **MCP-style tools** (`tools.py`) — a tool registry with typed input
  schemas, validation before dispatch, and a full call trace:
  `search_kb`, `lookup_policy`, `escalate_to_human`, `log_feedback`.
- **Retrieval agent** (`agent.py`) — plan → retrieve → answer with
  citations → validate. Answers only from retrieved sentences; a
  question with no grounding document escalates to a human instead of
  inventing an answer.
- **Rubric graders** (`graders.py`) — correctness against expected
  facts, grounding in cited documents, safety (PII leak detection),
  latency and cost. Deterministic stubs; a model-backed grader plugs
  into the same `grade()` interface.
- **Evaluation harness** (`harness.py`) — run representative cases,
  score them, and write a JSONL observability log (one record per case
  plus a summary record) so runs can be replayed and compared.
- **Production-readiness gate** (`readiness.py`) — explicit thresholds
  on pass rate, grounding, p95 latency, cost per case and PII leaks.
  The demo exits non-zero while any check fails.
- **Deployment playbook** (`playbook.py`) — renders a Markdown
  playbook from a run: eval evidence, readiness verdict, rollout
  steps, risks. The artifact that makes the next deployment reusable.

## Run it

```bash
PYTHONPATH=. python3 -m pytest tests/ -q   # 29 tests
PYTHONPATH=. python3 run_demo.py            # intake -> eval -> gate -> playbook
```

The demo picks the support-knowledge-assistant use case, runs 5 eval
cases, applies the readiness gate and writes `playbook.md` and
`evaluation_log.jsonl`. A question with no grounding document (for
example flight refunds) is covered in the tests: it escalates to a
human and fails the gate, which is the gate working as designed.

## Layout

```text
enterprise_ai_deployment/
  __init__.py      public API
  intake.py        use-case scoring and ranking
  retrieval.py     document store and citations
  tools.py         MCP-style tool registry
  agent.py         deterministic retrieval agent
  graders.py       rubric graders (correctness, grounding, safety, cost)
  harness.py       eval runner and JSONL observability log
  readiness.py     production-readiness gate
  playbook.py      reusable deployment playbook generator
tests/             29 pytest tests
run_demo.py        end-to-end demo
```

## Why this project is different from the others in the repo

- `commercial-agent-eval-harness` evaluates two agents against
  acceptance criteria; it has no use-case intake, no readiness gate
  and no playbook.
- `edu-ai-evaluation-guardrails` grades tutor responses for education;
  it has no retrieval, no enterprise tools and no deployment playbook.
- `agentic-service-delivery-platform` rolls out software services; it
  is not an AI deployment and has no eval harness or graders.
- `rag-data-patterns-evaluator` tests RAG patterns in isolation; it
  does not take a use case from intake to a production decision.

This project is the full prototype-to-production loop for one
enterprise customer deployment, which is what the OpenAI Applied AI
Engineer, Mid-Market Enterprise role asks for.
