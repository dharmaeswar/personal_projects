# Investment Research AI Assistant

Role project for T. Rowe Price — Investment AI Solutions Analyst, Req 81557 (Baltimore, MD).
An analyst/PM research copilot: retrieval-augmented Q&A over investment research notes
(earnings-call style notes, filing excerpts, analyst notes), with grounded answers that cite
their sources, retrieval evaluation, compliance guardrails, and observability logging.

All documents are **synthetic, seeded, fictional** research notes written for this demo.
No real company data, no T. Rowe Price affiliation, no live LLM call: the answer
composer is a deterministic extractive stand-in that only repeats what the retrieved
passages say, so groundedness can be measured exactly.

## What it is

- `research_assistant/corpus.py` — seeded corpus of 12 fictional research documents
  (earnings notes, 10-K style excerpts, analyst notes, risk memos) with source metadata.
- `research_assistant/chunking.py` — splits documents into passages (max ~120 words,
  sentence-aware, keeps source + section metadata on every chunk).
- `research_assistant/retrieval.py` — TF-IDF-weighted keyword retrieval over chunks
  (stdlib only, deterministic). Returns ranked passages with scores.
- `research_assistant/qa.py` — grounded Q&A: retrieves top-k passages, composes an
  answer only from retrieved text, attaches a citation to every claim, and says
  "not covered by the research notes" instead of inventing an answer when nothing
  retrieved is relevant.
- `research_assistant/guardrails.py` — compliance checks on every answer: no claim
  without a citation, no forward-looking guarantee language, no material-non-public
  information markers, no recommendation to buy/sell a specific security.
- `research_assistant/evaluate.py` — retrieval + groundedness evaluation over a seeded
  Q&A set: recall@k, groundedness rate, hallucination-flag rate, guardrail pass rate.
- `research_assistant/observability.py` — JSONL run log of every query (question,
  retrieved doc ids, scores, guardrail verdict, latency).
- `run_research_demo.py` — runner: answers three sample analyst questions, prints the
  answers with citations, runs the evaluation, writes `research_eval_report.json`.

## How to run

```bash
python -m pytest -q
python run_research_demo.py
```

## Honest limits

- Synthetic seeded corpus only; no real filings, earnings calls, or market data.
- The answer composer is extractive and deterministic, not a deployed LLM agent;
  no LangChain / LangGraph / AutoGen integration is claimed.
- Retrieval is TF-IDF keyword matching, not embeddings; it is a working baseline
  with measured recall, not a production search system.
- Guardrails are rule-based checks, not a compliance review; they demonstrate the
  control pattern, not legal sign-off.
