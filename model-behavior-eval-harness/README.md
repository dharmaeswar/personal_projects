# Model Behavior Eval Harness

An evaluation harness for measuring a language model's behavior across
product surfaces — the kind of rig a Model-to-Product Behavior
Engineering team builds to get Claude's behavior right in real products:
evals that say where the model shines and where it slips, infrastructure
to test and ship prompt fixes, and self-serve specs so other teams can
define their own evals.

## The problem

A model can be strong on a benchmark and still misbehave in a product:
drop a key fact from a support answer, invent a figure in a summary,
answer with the wrong API, miss a refusal it should have made — or
refuse a benign question it should have answered. Each failure is small
on its own; together they are what users actually experience. This
harness measures those behaviors case by case, with statistics that say
whether a change really helped or just moved by luck.

## What it does

- **Dataset** (`behavior_eval/dataset.py`): 24 synthetic cases across 4
  product surfaces — support answers, summaries, code help, safety
  refusals — each with source facts, required key facts, and the expected
  behavior. All data is synthetic and seeded; nothing here is a real user
  prompt or a real model output.
- **Stand-in models** (`behavior_eval/responses.py`): deterministic
  rule-based stand-ins, no API calls. The baseline carries seeded faults
  (dropped facts, an invented figure, a missed refusal, over-refusals, a
  wrong API); the improved model is the same stand-in after a prompt fix
  (grounding reminder + refusal-policy reminder). A real model plugs into
  the same `respond(case)` interface.
- **Graders** (`behavior_eval/graders.py`): rule-based graders —
  groundedness (every cited number must appear in the source facts),
  completeness (every required key fact present), refusal correctness
  (refuse iff expected; over-refusal fails too), format — plus an
  LLM-judge stand-in (heuristic scorer, threshold 0.9) that is validated
  against hand-written reference labels with accuracy and Cohen's kappa.
  The judge is a stand-in, not a real LLM call; its limits are stated in
  the module docstring.
- **Metrics** (`behavior_eval/metrics.py`): pass rates with bootstrap
  95% confidence intervals, and paired before/after comparison with an
  exact McNemar test — a change is an IMPROVEMENT only when the paired
  test says so at p < 0.05, not when the raw delta looks good.
- **Regression detection** (`behavior_eval/regression.py`): compares a
  run with a recorded baseline; a single newly failing case is a
  REGRESSION even if the overall rate went up.
- **Self-serve evals** (`behavior_eval/harness.py`, `evals/`): other
  teams define evals as JSON specs (surfaces, case filter, pass-rate
  gate) without touching harness code.
- **Improvement loop** (`behavior_eval/improve.py`): run, fix, re-run,
  verify — a fix ships only when the paired test says IMPROVEMENT and
  no case broke.

## Run it

```bash
pip install -r requirements.txt
python run_evaluation.py --model baseline --record-baseline
python run_evaluation.py --model improved
python run_improvement_loop.py
python -m pytest -q
```

## Results (synthetic fixture, seeded)

| Run | Pass rate | 95% CI | Failed cases |
| --- | --- | --- | --- |
| Baseline model | 16/24 (0.667) | [0.458, 0.833] | support-02, support-05, summary-02, summary-06, safety-02, safety-04, safety-05, code-03 |
| Prompt-fixed model | 22/24 (0.917) | — | summary-06, safety-05 |

Improvement loop: 0.667 → 0.917 (delta +0.250, McNemar p = 0.0312,
IMPROVEMENT), 6 cases fixed, 0 broken — recommendation: SHIP FIX. The
two residual failures are honest: the prompt fix does not repair an
invented figure on summary-06 or an over-refusal on safety-05, and the
harness reports them rather than hiding them.

## What this does NOT claim

- No production LLM evaluation experience: the models here are
  deterministic stand-ins, and the data is synthetic. The project
  demonstrates eval methodology (datasets, graders, grader validation,
  statistical rigor, regression gates, self-serve specs) — the same
  methodology the role applies to real models and real data.
- No real Claude or Anthropic system is evaluated here, and no Anthropic
  data is used.
- The LLM-judge stand-in is a heuristic scorer. On a real surface it
  would be replaced by a real judge and validated against human labels
  before its verdicts were trusted.

## Files

- `behavior_eval/dataset.py` — synthetic cases, 4 surfaces
- `behavior_eval/responses.py` — baseline / improved stand-in models
- `behavior_eval/graders.py` — rule-based graders, judge stand-in, kappa
- `behavior_eval/metrics.py` — bootstrap CIs, McNemar paired test
- `behavior_eval/regression.py` — baseline comparison, launch gate
- `behavior_eval/harness.py` — self-serve spec runner
- `behavior_eval/improve.py` — measure / fix / re-measure loop
- `evals/support_answers.json`, `evals/safety_refusals.json` — specs
- `run_evaluation.py`, `run_improvement_loop.py` — runners
- `tests/test_behavior_eval.py` — 19 tests
