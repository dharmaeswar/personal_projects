# Support Quality & Coaching Evaluator

LLM-as-judge quality evaluation, AI coaching, and agent training simulation
for customer-support teams — the shape of system Airbnb's Assistance
Foundations group builds: LLM-based quality evaluation that scores support
cases against the quality standard at scale, AI coaching that turns quality
evidence into coaching plans, simulation environments that train agents on
realistic support scenarios, and natural-language search over help-center
knowledge so agents find answers faster.

All cases, transcripts, knowledge-base articles, and labels are synthetic
demo data. Nothing here describes a real platform, real customers, or a
real deployment. Python standard library only — no third-party runtime
dependencies (pytest is the only dev dependency). No model API calls: the
built-in judge is a deterministic, rule-based stand-in with seeded
behaviour, so every run is reproducible offline. A model-backed judge
plugs into the same `grade()` interface.

## What it does

- **Rubric-based LLM-as-judge** (`support_quality/judge.py`) — scores
  each support case on five criteria (accuracy, empathy, policy
  compliance, resolution, clarity) on a 0–2 scale, with a weighted
  overall score, per-criterion evidence strings, and a pass/fail bar.
  Two prompt versions (`v1`, `v2`) let prompt changes be A/B-tested
  instead of assumed better.
- **Retrieval over the help-center KB** (`support_quality/retrieval.py`)
  — deterministic TF-IDF ranking over synthetic help-center articles,
  returning ranked answers with citations the agent can quote.
- **AI coaching plans** (`support_quality/coaching.py`) — turns quality
  evidence into a coaching plan: weakest criteria first, each with a
  drill, a target score, a linked KB article, and a simulation scenario.
- **Simulation environments** (`support_quality/simulation.py`) —
  scripted guest/host scenarios where a trainee agent replies turn by
  turn; each reply is scored against the rubric and the session ends
  with a coaching plan.
- **Offline + online evaluation** (`support_quality/evaluation.py`) —
  runs the judge over the human-labeled case set and reports agreement
  with human labels (exact-match rate and mean absolute error per
  criterion), compares prompt versions head to head, and applies a
  release gate so a worse prompt version cannot ship silently.
- **Dataset engineering** (`support_quality/data.py`) — the labeled case
  set, the KB, and the simulation scenarios live in one place with a
  completeness check (every case carries human labels on every
  criterion), so eval data stays curated instead of drifting.
- **Production observability and outcome tracking** (`support_quality/outcomes.py`, new, Nov 2026 — built for a Toast Software Engineer II, Support AI role) — watches the system that serves the conversations: per-conversation outcomes (channel, resolved-without-human, escalated, turns, per-turn latency, vendor, vendor errors, CSAT, cost), a summary (resolution/escalation rates, mean and p95 latency, vendor error rate, mean CSAT, cost per conversation), a release-regression check (resolution drop or p95 latency rise vs baseline), per-vendor health against an SLO (error rate, p95 latency, breach flag), and an on-call alert check. On the seeded panel (400 conversations): resolution 68%, escalation 38%, mean latency 667ms, p95 1182ms, vendor error rate 2.0%, mean CSAT 4.3; the seeded unreliable vendor (3.8% errors) breaches its SLO while the reliable one (1.1%) does not.

## Run it

```bash
python3 run_demo.py            # end-to-end demo: retrieve, grade, coach, simulate, evaluate
python3 -m pytest tests/ -q    # test suite
```

## Layout

```
support_quality/
  data.py        # rubric, synthetic cases + human labels, KB articles, scenarios
  judge.py       # rule-based LLM-as-judge (grade interface), prompt versions
  retrieval.py   # TF-IDF retrieval over the help-center KB
  coaching.py    # coaching plans from quality evidence
  simulation.py  # training simulations scored turn by turn
  evaluation.py  # offline agreement, prompt A/B, release gate
  outcomes.py    # production observability: resolution, latency, vendor SLOs, alerts
run_demo.py
tests/
  test_judge.py test_rest.py test_outcomes.py
```
