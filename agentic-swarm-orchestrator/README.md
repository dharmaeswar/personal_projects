# Agentic Swarm Orchestrator

Role project for **Ramp — Research Engineer, Agentic Systems** (Ashby
f90d32c1-7c10-4161-8913-075e1b423697): a fan-out agent swarm that searches a
large space, merges partial results, verifies them, and measures what each
useful result costs.

The JD's problem, in miniature: most agent work is one agent, one trace,
and a person reads the result. This system fans thousands of agents (16
here, at demo scale) out over a large search space, and an orchestrator
turns their partial results into one ranked, verified answer set.

All data is synthetic and seeded. No network calls, no live LLM calls, no
credentials. Standard library only, plus pytest for tests. Agents are
deterministic simulated models (a cost/latency/accuracy contract plus a
seeded draw per model/doc/question), so every run is reproducible offline.

## What it does

- **Fan-out map** (`swarm/orchestrator.py`): the corpus is split into
  disjoint shards; one agent scans each shard in parallel in a thread
  pool. Shards are launched in waves.
- **Agentic map-reduce**: partial results are deduplicated (best score
  per document wins) and ranked by score.
- **Verification** (`swarm/verify.py`): candidates are re-checked by an
  independent model pass; voting/consensus across agents and sampling
  verification are provided alongside full verification. Quality is
  measured as precision and recall against ground truth.
- **Model routing** (`swarm/models.py`): the cheapest model that fits the
  budget and the question's complexity handles the map phase; the
  expensive model is spent only on verification. Three profiles:
  scout-small ($0.002/doc, recall 0.62), standard ($0.010/doc, recall
  0.85), reasoner-large ($0.050/doc, recall 0.96).
- **Cost and latency per useful result** (`swarm/metrics.py`): every run
  reports cost, simulated latency, precision, recall, cost per useful
  result, and yield per dollar — computed from the run, never hand-written.
- **Caching**: shard results and verification outcomes are memoized, so a
  repeat search re-scans nothing and costs $0.00.
- **Early stopping**: when a wave of agents adds no new verified results,
  the run stops instead of burning budget on the remaining shards.

## Run it

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python run_demo.py
python run_evaluation.py
```

## Measured results

Demo — one question, 1,200 documents, 120 true answers, 16 agents,
scout map + reasoner verification:

| | Results | Precision | Recall | Cost | Cost / useful result | Latency |
|---|---|---|---|---|---|---|
| First run | 83 verified | 0.807 | 0.558 | $9.95 | $0.1485 | 3.20 s |
| Second run (cached) | 83 verified | 0.807 | 0.558 | $0.00 | $0.00 | 0.20 s |

Evaluation — six seeded questions, three configs (`swarm_eval_report.json`):

| Config | Mean precision | Mean recall | Total cost | Total latency |
|---|---|---|---|---|
| Single agent, standard, no verification | 0.755 | 0.854 | $72.00 | 288.3 s |
| Fan-out 16, standard, no verification | 0.755 | 0.854 | $72.00 | 73.2 s |
| Full swarm: scout map, reasoner verify, cache, early stop | 0.884 | 0.603 | $62.10 | 19.2 s |

Read the tradeoff honestly: the fan-out alone buys latency (4x faster than
one agent at the same cost and recall — the same scan set, run in
parallel). The full swarm buys precision (+0.13) and latency (15x faster
than the single agent) and a lower bill, but the cheap map model costs
recall (−0.25): the scout misses answers the standard model would have
found. That is the tradeoff the system exists to measure — which model
handles which step, and when more agents stop helping — not a claim that
one config wins on every axis.

## Test results

**21 passed, 0 failed** (goal venv Python 3.12, pytest 9.2.0).

Coverage: corpus determinism and ground truth; shards cover every
document exactly once; scan determinism; reasoner recalls more than the
scout; router picks the cheapest model that fits; voting thresholds;
precision/recall math; sampling estimation; verification keeps true
positives and drops false positives; ranked verified results; fan-out
matches single-agent recall at lower latency; no verification means lower
precision; cache makes a repeat search free; early stopping when later
waves add nothing; budget cap stops the run; empty corpus; cost-per-useful
math; doubling agents past full coverage adds no recall.

## Honest limits

- Simulated models, not real LLMs: accuracy, cost, and latency are
  contracts in `swarm/models.py`, not measurements of a hosted model.
  The numbers show the orchestration mechanics, not production model
  quality.
- Demo scale: 1,200 documents and 16 agents, threaded in one process —
  not thousands of agents across a distributed system, and simulated
  latency is not a production benchmark.
- The corpus is seeded and balanced (one topic in ten documents), so
  recall/precision figures describe this corpus, not arbitrary corpora.
- No Ray, Temporal, or Modal: the orchestrator is a custom fan-out built
  on `concurrent.futures`. No post-training and no open-source model
  hosting are claimed.
