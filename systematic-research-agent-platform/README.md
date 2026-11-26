# Systematic Research Agent Platform

Role project for Man Group — Senior Python Developer, Systematic Applied AI
(Boston). A multi-agent research platform for a systematic investment
business: a knowledge layer over research notes, research code, and datasets;
planner, retriever, executor, and validator agents that run a research
question end to end; an MCP-style tool registry; and an evaluation harness
that scores agent trajectories and gates releases on regression results.

All documents, figures, and return series are **synthetic and seeded** for
this demo. No real Man Group research, code, or market data is used, and no
live LLM call is made: the agents are deterministic rule-based policies, so
every run is reproducible offline.

## The problem

Applied AI for systematic research needs three things at once: agents that
can find the right evidence across code, research, and data; a knowledge
layer that makes that evidence citable; and evaluations that say whether a
change to a model, prompt, or tool actually made the agent more reliable.
Without the evaluation layer, a new agent version can look better in a demo
and silently get worse at grounding its answers.

## What it is

- `research_platform/corpus.py` — seeded corpora: 4 research notes
  (momentum, FX carry, volatility targeting, mean reversion), 2 Python
  research-code documents, 3 dataset summaries with factor statistics.
- `research_platform/chunking.py` — sentence-aware passage chunking
  (max ~120 words) that keeps document id, kind, and title on every chunk.
- `research_platform/knowledge_layer.py` — deterministic TF-IDF-weighted
  keyword retrieval over the three corpora, with per-kind filtering.
- `research_platform/tools.py` — MCP-style tool registry: `search_knowledge`,
  `read_code`, `compute_statistic`, `validate_number`. Unknown tools and
  missing parameters raise; every call is logged for replay.
- `research_platform/agents.py` — planner (decomposes a question into
  subtasks), retriever, executor (sandboxed statistics through tools),
  composer (answers only from retrieved evidence, one citation per claim),
  validator (re-checks every number against dataset ground truth).
- `research_platform/orchestrator.py` — the long-horizon loop: plan →
  retrieve → execute → compose → validate, with one repair pass inside a
  step budget when validation fails.
- `research_platform/evaluate.py` — trajectory evals over 6 seeded tasks:
  groundedness, citation coverage, figure correctness, tool-use accuracy,
  reproducibility; plus a baseline-vs-improved regression report with a
  release gate.
- `research_platform/observability.py` — JSONL run log of every research run.

## How to run it

```bash
pip install -r requirements.txt
python run_research_demo.py     # one multi-agent research question
python run_evaluation.py        # baseline vs improved regression report
python -m pytest tests/ -q      # 25 tests
```

## Measured results (seeded 6-task eval, `research_eval_report.json`)

| Config | Grounded rate | Citation coverage | Figures correct | Tool accuracy | Reproducible |
|---|---|---|---|---|---|
| Baseline (no validator, single pass) | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Improved (validator + one repair pass) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Release gate passed: the improved config does not regress groundedness or
citation coverage (grounded rate +1.00, citation coverage +0.00).

Note on the baseline grounded rate of 0.00: groundedness is defined as
"the validator passed". The baseline runs no validator, so no run can claim
groundedness — that is the point of the comparison, not a claim that the
baseline answers were wrong (its figures were correct in 6/6 tasks).

## Honest limits (also stated here, not hidden)

- Synthetic seeded corpora only; no real research, code, or market data.
- Agents are deterministic rule-based policies, not LLM agents; no
  LangChain / LangGraph / AutoGen / MCP-server integration is claimed.
- Retrieval is TF-IDF keyword matching, not embeddings; a working baseline
  with measured recall, not a production search system.
- The seeded return series are constructed to match the dataset figures, so
  computed statistics corroborate the corpus by design; they are not
  independent evidence.
- The validator re-checks numbers against seeded ground truth; it is not a
  compliance review and does not judge research quality.
