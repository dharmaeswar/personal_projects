# Commercial Bank Multi-Agent RAG

A multi-agent retrieval-augmented generation system that answers
commercial-banking questions over numeric financial statements and textual
credit memos — the kind of Applied AI system the Capital One Commercial
Bank Data Science team builds: multi-agent orchestration, advanced RAG
over numeric and textual data, context engineering, evaluation and
validation, and deployment-ready reporting.

All borrowers, figures and memos are synthetic and invented. No real bank,
borrower or account data is used. No real LLM or API calls: the agents are
deterministic rule-based policies with seeded data, so every run is
reproducible offline. A real LLM (LangChain) agent plugs into the same
`plan / retrieve / answer / validate` interfaces.

## The problem

A commercial-banking question mixes two kinds of evidence. "Is BlueRock in
compliance with its leverage covenant?" needs exact figures (debt, EBITDA,
interest) to compute ratios AND the covenant text for the limits. A plain
text search ranks the memo above the figures table and drops the operands;
a plain table lookup cannot answer "what does the memo say about
supply-chain risk?". This pipeline runs four agents so each question gets
the right evidence, the answer is computed from that evidence only, and a
validator re-checks every number before the answer ships.

## The four agents

- **Planner** (`agents.py`): splits a question into subtasks — numeric
  lookup, text lookup, ratio computation, covenant check.
- **Retriever** (`agents.py`, `retrieval.py`): hybrid retrieval — an exact
  numeric-table lookup (ratio questions also pull the operands the ratio
  needs; comparison questions pull the metric for every borrower) plus
  TF-IDF text search, then context engineering (`context.py`): numeric
  facts first, duplicate sentences dropped, packed into a character
  budget with citations kept.
- **Analyst** (`agents.py`): composes the answer from the packed context
  only. Ratios are computed from figures parsed out of the context, with
  the formula shown; covenant verdicts are computed from the same
  figures. If a needed figure is missing, it says so instead of guessing.
- **Validator** (`agents.py`): re-checks every number in the answer — it
  must appear verbatim in the context or be recomputable from the context
  figures. The analyst's own computed values are never trusted; they are
  recomputed here. Covenant verdicts are recomputed the same way.

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py "Is BlueRock Packaging Co in compliance with its leverage covenant?"
python run_evaluation.py     # 8 seeded cases; exit 0 when all pass and grounded
python -m pytest -q          # 26 tests
```

`run_pipeline.py` writes `pipeline_report.txt`; `run_evaluation.py`
writes `evaluation_report.txt`.

## Results (seeded, reproducible)

| Metric | Result |
| --- | --- |
| Answer accuracy (8 seeded cases) | 100% |
| Groundedness (validator PASS) | 100% |
| Citation coverage | 100% |
| Tests | 26/26 pass |

Example — covenant check:

```
Q: Is BlueRock Packaging Co in compliance with its leverage covenant?
Plan: numeric-lookup, text-lookup, compute-ratio, covenant-check
A: BlueRock Packaging Co is in breach: leverage 4.00x against a maximum
   of 3.5x, interest coverage 2.00x against a minimum of 2.0x.
Validation: PASS
```

The harness caught real design faults while it was built: an early version
let the analyst compute ratios from the figures table behind the corpus
instead of from retrieved context, so the validator (correctly) flagged
the operands as ungrounded; and the retriever's text cap cut numeric
facts, so comparison questions saw only one borrower. Both are fixed:
the analyst parses figures only from context, and the cap applies to
text hits, not numeric facts.

## Layout

- `bank_rag/corpus.py` — synthetic borrowers, figures, memos, covenants
- `bank_rag/retrieval.py` — TF-IDF text index, numeric lookup, hybrid retrieval
- `bank_rag/context.py` — context engineering: budget, dedup, citations
- `bank_rag/agents.py` — Planner, Retriever, Analyst, Validator
- `bank_rag/pipeline.py` — plan → retrieve → analyse → validate
- `bank_rag/evaluate.py` — seeded eval set and metrics
- `run_pipeline.py`, `run_evaluation.py` — CLI entry points
- `tests/` — 26 pytest tests

## Notes and limits

- The ranker is a TF-IDF baseline, not a neural embedding model, and
  there is no vector database — it measures the pipeline, not embedding
  quality. A real embedding model and vector store can replace
  `TextIndex.score` without changing the pipeline.
- No cloud services (no AWS/Spark/PyTorch/LangChain in the demo); the
  interfaces are shaped so those swap in without changing the agents.
- No fine-tuning in the demo: the pipeline covers context engineering,
  evaluation, validation and deployment reporting; a fine-tuned generator
  would replace the Analyst's rule-based composition.
