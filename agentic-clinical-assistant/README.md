# Agentic Clinical Assistant

A customer-facing agentic AI assistant for care teams, built as a portfolio
project, updated for a Johnson & Johnson Senior AI Engineer application:
GenAI/LLM applications, RAG, semantic search, AI agents, and healthcare
Real-World Data (RWD) analytics in Python and SQL-style data processing. It answers
care-team questions by retrieving guidance from a knowledge base, calling
tools over patient context, drafting summaries, and escalating urgent cases —
with a clinician in the loop for anything that leaves the system.

**All data is synthetic and local.** No real patients, no real clinical
guidance, no real health records, no model API calls, no network access.
Nothing here is a claim about any real company's systems, and this is a demo
safeguard design, not a HIPAA certification.

## What it does

- **RAG retrieval** (`clinical_agent/retrieval.py`) — deterministic TF-IDF
  ranking over a synthetic care-guidance knowledge base, so retrieval is
  reproducible and testable without a vector database or model calls.
- **Tool-calling agent** (`clinical_agent/agent.py`) — plans a short tool
  sequence per request inside a 6-step budget: search the knowledge base,
  pull de-identified patient context, draft a summary, escalate urgent
  symptoms, or draft a patient message.
- **Tool server** (`clinical_agent/tools.py`) — five validated tools with
  schemas and per-call tracing (tool, args, latency, outcome). Read tools
  run freely; `escalate_to_clinician` and `send_message` require explicit
  human approval, and a missing approval is a denial that is traced and
  reported, never silently skipped.
- **PHI protection** (`clinical_agent/phi.py`) — names, MRNs, dates of birth,
  phone numbers, emails and SSN-shaped strings are redacted before anything
  is written to the audit log, and patient context returned to the agent is
  de-identified by design (conditions and medications only).
- **Audit log** (`clinical_agent/audit.py`) — append-only, timestamped,
  actor + action + redacted detail, so any request can be replayed.
- **Real-World Data analytics** (`clinical_agent/rwd.py`) — synthetic
  claims-like records generated locally (no real patient data): cohort
  building by condition / procedure / drug, longitudinal patient-journey
  summaries (events over time), treatment-pattern and healthcare-utilization
  aggregates, and data-quality / completeness checks. Exposed to the agent
  as the `analyze_rwd` tool, triggered by cohort / claims / utilization /
  treatment-pattern / patient-journey requests. Codes are simple synthetic
  labels only — not ICD-10-CM, CPT/HCPCS, NDC or RxNorm work.
- **Data pipeline** (`clinical_agent/pipeline.py`) — validates FHIR-shaped
  interoperability records, de-duplicates them, builds per-patient features,
  and loads them into the feature store and vector store, with a run report
  (received / loaded / rejected / duplicates) so a bad feed is visible.
- **Vector store + feature store** (`clinical_agent/vector_store.py`) —
  deterministic in-memory vector store (hashed embeddings, cosine search,
  metadata filters) and a versioned feature store so a model trained on v1
  features can be reproduced after v2 is published. Embeddings here are
  deterministic hashes for testing, not production model embeddings.
- **Eval suite** (`clinical_agent/evals.py`) — six acceptance cases: the
  agent must use the right tools, must hold sends and escalations for
  approval, must escalate when approved, and must never leak PHI into logs.

## How it differs from the other projects in this repo

- `commercial-agent-eval-harness` evaluates agents against acceptance
  suites; this project **is** the customer-facing agent (RAG + tool calls +
  human review + audit).
- `rag-data-patterns-evaluator` only compares chunking strategies for
  retrieval; this project builds the full retrieval-to-action loop.
- `agentic-service-delivery-platform` is an agent for deployment rollouts;
  this one serves care-team workflows in a regulated setting.
- `llm-rollout-toolkit` is a sampling/tokenizer library; this one is an
  end-to-end applied AI service.

## Run it

```bash
python run_assistant.py
python run_assistant.py --request "Review this patient's blood pressure medication." --patient P-1002
python run_assistant.py --request "The patient reports chest pain." --patient P-1001 --approve
python run_assistant.py --eval
```

## Test it

```bash
python -m pytest tests/ -q
```

## Layout

- `clinical_agent/kb.py` — synthetic care-guidance docs and patient roster
- `clinical_agent/retrieval.py` — TF-IDF retrieval over the knowledge base
- `clinical_agent/phi.py` — PHI detection and redaction
- `clinical_agent/tools.py` — validated tool server with tracing and approval gates
- `clinical_agent/agent.py` — planner, step budget, human-in-the-loop loop
- `clinical_agent/audit.py` — append-only redacted audit log
- `clinical_agent/rwd.py` — synthetic RWD: cohorts, journeys, treatment patterns, utilization, data quality
- `clinical_agent/vector_store.py` — deterministic vector store and versioned feature store
- `clinical_agent/pipeline.py` — interoperability ingest pipeline with validation, dedupe and run reports
- `clinical_agent/evals.py` — acceptance eval cases
- `run_assistant.py` — demo CLI (`--eval` runs the suite)
- `tests/` — pytest suite
