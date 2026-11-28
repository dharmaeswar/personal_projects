# Governed GenAI Cloud Platform

The shared platform that lets a bank's teams use generative AI safely —
the work the Texas Capital Bank Senior Cloud Engineer role does: AWS
cloud platform engineering, a Bedrock model gateway, retrieval-augmented
generation, LangChain/LangGraph-style orchestration, governed agents,
automated evaluation, and observability and cost by team and use case.

Built as the role project for the Texas Capital Bank — Senior Cloud
Engineer (JR106432) application. All data is synthetic and seeded. No
real AWS calls, no real Bedrock calls, no real customer or borrower data.
The generator and agent tools are deterministic stand-ins so every run
is reproducible offline; a real Bedrock client and real LangChain /
LangGraph primitives plug into the same interfaces.

## What it does

- **Cloud platform as code** (`genai_platform/iac.py`) — the platform as
  a Terraform-style plan: VPC and subnets, least-privilege IAM roles,
  EKS and Lambda runtimes, encrypted S3 data stores, Bedrock model
  access. `validate()` enforces the guardrails as code: required
  cost/owner tags, no public data subnets, no wildcard IAM actions,
  encryption at rest, versioned stores, replica minimums.
- **Bedrock model gateway** (`genai_platform/gateway.py`) — the single
  front door for model calls: a registry of Bedrock models with
  cost/latency figures, routing with failover to the healthy model with
  the most capacity headroom, guardrails (PII redaction, blocked
  topics), versioned prompt templates, and per-call metering (tokens,
  cost, latency) by team and use case.
- **RAG** (`genai_platform/rag.py`) — TF-IDF retrieval over seeded bank
  policy/runbook documents, packed into a character budget with
  citations kept. A question with no supporting chunk says so instead
  of guessing. A Bedrock Knowledge Bases vector store plugs into the
  same `retrieve` interface.
- **Orchestration** (`genai_platform/orchestration.py`) — a LangChain /
  LangGraph-style state graph: plan → retrieve → generate → validate.
  The generator composes an extractive answer from the retrieved
  context only; the validator checks the answer is grounded in that
  context before it ships.
- **Governed agents** (`genai_platform/agents.py`) — tools carry the
  scopes they need and nothing more; calls run sandboxed against
  seeded data; consequential actions (payments, record updates,
  customer contact) need a human approval before they run; every
  prompt, tool call and output lands in an audit log.
- **Evaluation** (`genai_platform/evaluation.py`) — 8 seeded cases
  (accuracy, safety) run through the graph as the regression suite for
  the delivery pipeline, plus observability: latency, token use and
  cost by team, use case and model, and a cheapest-passing-model
  recommendation.

## Run it

```bash
pip install -r requirements.txt
python run_platform.py    # IaC validation, RAG answer, governed agent task, cost summary
python run_evaluation.py  # 8 seeded eval cases; exit 0 when all pass
python -m pytest -q       # 38 tests
```

## Results (seeded, reproducible)

| Check | Result |
|---|---|
| IaC plan validation | 0 violations (4 subnets, 2 IAM roles, 2 runtimes, 2 stores, 3 Bedrock models) |
| RAG answer, covenant limit question | "The leverage covenant limit is 3.5x debt to EBITDA…" with POL-101 citation, grounded |
| Governed agent | lookup + covenant check pass; payment without approval refused; with approval runs; 10 audit entries |
| Evaluation | 8/8 pass (accuracy 6/6, safety 2/2) |
| Gateway metering | 1 call, 33 tokens, $0.000315, 900 ms p50 |

## Honest limits

- Synthetic demo data and planning cost figures, not a live price list
  or a real AWS account; nothing here contacts AWS or Bedrock.
- The generator is an extractive stand-in, not a real LLM; LangChain,
  LangGraph and OpenClaw are named as the frameworks the graph mirrors,
  not imported or run — no production LangChain/LangGraph, Bedrock RAG
  or agent-runtime experience is claimed.
- Terraform, Kubernetes and EKS are modelled as plan definitions and
  validation rules in Python, not as applied `.tf` files against a real
  cluster; no production cloud-platform ownership is claimed.
- No Texas Capital data, systems or customers are involved.
