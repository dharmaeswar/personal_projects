# Agentic Analytics Statistical Evaluator

An agentic analytics pipeline whose claims are **statistically validated**,
not just stated. Three agents run a full analytics pipeline over a synthetic
two-arm experiment dataset — then a validator re-tests every claim with real
statistics and only the claims that survive get a PASS.

## The problem

Agentic AI can plan analyses, run code and write up findings fast. But an
agent that reports "significant" from one uncorrected p-value will also
report noise as a finding. This evaluator shows the missing layer: a
statistical validation gate between an agent's claims and the report.

## What it does

1. **Planner agent** turns the question into an ordered plan (describe,
   test primary, test secondary, test responder rate, test subgroup, validate).
2. **Analyst agent** runs the plan and states four claims from uncorrected
   p-values — the way an unchecked agent would.
3. **Validator agent** re-tests every claim with:
   - Welch's two-sample t-test and chi-square test (implemented from scratch,
     standard library only — no SciPy)
   - Bootstrap 95% confidence intervals for the mean difference
   - Cohen's d effect size and a power check
   - Bonferroni correction across all claims
   - A direct interaction test for subgroup claims ("helps group X even more"
     is an interaction claim, not a subgroup p-value)

## Run it

```bash
pip install -r requirements.txt
python run_evaluation.py     # prints the report, writes evaluation_report.txt
python -m pytest -q          # 53 tests (34 pipeline + 19 evals)
```

## Product experimentation (new, Nov 2026)

A product-experimentation layer on the same seeded dataset: power-based
A/B test design (sample size per arm, days to run), metric guardrails that
fail a rollout on a significant regression, O'Brien-Fleming sequential
monitoring so interim peeking stays safe, and a SHIP / DO NOT SHIP readout.
On the demo data the primary effect (+10.84, 95% CI (8.0, 13.68), power
1.0) ships with the guardrail passing; the design needs 98 users per arm
for a minimum detectable effect of 5.0.

## Agentic evals layer (new, Nov 2026 — Iterable Nova fit)

The same project now also evaluates *agent behaviour*, not just
analytics claims: `agentic_stats/evals.py` is an LLM-judge harness for
multi-turn agent trajectories, the way an agentic product has to be
evaluated before it ships.

- **Rubric judge** (`judge_trajectory`): scores a trajectory on
  grounding (answer claims backed by tool results), tool use (valid
  tools, required args, a result for every call), coherence (numbers
  in the answer match the evidence) and reasoning (reasoning steps
  cite the evidence). Hallucinated numbers and invalid tool calls are
  hard fails, whatever the mean score says.
- **Synthetic data pipeline** (`generate_synthetic_cases`): seeded
  benchmark of clean trajectories plus known-bad mutations —
  hallucinated claim, unknown tool, missing tool result, unsupported
  answer — each with an expected verdict.
- **Regression detection** (`detect_regression`): Welch t-test plus
  bootstrap 95% CI on the score difference, so a drop is only called
  a regression when it is real, not noise.
- **Failure diagnosis** (`diagnose_failures`): maps each failure to
  the fix it needs — prompt, tool, context, rubric, or harness.

```bash
python run_evals.py        # prints the report, writes evals_report.txt
python -m pytest -q        # 53 tests (34 original + 19 evals)
```

On the demo benchmark (10 seeded cases: 2 good, 8 mutated) the judge
agrees with the expected verdict on 10/10 cases, pass rate 20%, mean
overall score 0.836; the regression check against a second seeded run
finds no regression (mean diff +0.000, Welch p=1.0).

## Access propensity, wallet & attrition (added Nov 25, 2026)

`agentic_stats/access.py` adds the Digital-Agenda side of the same
statistical gate: propensity / ranking models for Access
opportunities, wallet and share-of-wallet models, and engagement /
attrition (time-to-event) analysis over a synthetic 240-client
interaction dataset (meetings, research reads, events, tenure).

- **Propensity** (`fit_logistic`, from scratch): test AUC **0.781**,
  train log-loss 0.393; calibration by decile, max gap 0.246.
- **Wallet** (`fit_ols`, from scratch): R² 0.811 train / 0.788 test;
  meetings, reads and events all carry positive weight, as the
  generator intends.
- **Attrition** (`kaplan_meier`, `attrition_by_engagement`):
  high-engagement clients attrite at 10.0% vs 34.3% for low
  engagement (chi-square 20.6, p < 0.001); 12-month survival 90.0%
  vs 65.7%.

Run it with `python run_access_eval.py` (writes
`access_eval_report.json`). Verdict on the seeded data: **PASS**.
Tests: 66 pytest tests pass (53 original + 13 new).

## What the demo data shows (240 synthetic rows, seed fixed)

| Claim | Analyst says | Validator verdict | Why |
| --- | --- | --- | --- |
| C1 — treatment improves the primary outcome | p ≈ 1.7e-12 | **PASS** | CI (8.0, 13.7) excludes zero, d = 0.96, power 1.0 |
| C2 — treatment improves the secondary outcome | p ≈ 0.997 | **FAIL** | CI includes zero; there is no effect to find |
| C3 — treatment raises the responder rate | p ≈ 1.9e-05 | **PASS** | 59.2% vs 31.7% responders, survives Bonferroni |
| C4 — treatment helps high-baseline participants even more | p ≈ 1.3e-05 | **FAIL** | Interaction p = 0.13 — the subgroup effect matches the overall effect |

C4 is the instructive one: the subgroup p-value is tiny, but the claim is
"even more", and the interaction test shows there is no extra benefit. A
p-value on the subgroup alone cannot support that claim.

## Layout

- `agentic_stats/access.py` — Access propensity (logistic regression),
  wallet OLS, Kaplan-Meier survival, attrition chi-square (pure stdlib)
- `agentic_stats/stats.py` — t-test, chi-square, bootstrap CI, Cohen's d,
  Bonferroni, power, interaction test (pure stdlib)
- `agentic_stats/experiments.py` — A/B test design, guardrails, O'Brien-Fleming
  sequential monitoring, experiment readout (pure stdlib)
- `agentic_stats/data.py` — deterministic synthetic two-arm dataset
- `agentic_stats/agents.py` — Planner, Analyst and Validator agents
- `agentic_stats/pipeline.py` — runs plan → analyse → validate → report
- `run_evaluation.py` — CLI runner
- `tests/` — pytest suite; reference values are textbook critical values
  (t = 2.228 at df = 10, chi-square = 3.841 at df = 1, both p = 0.05)

## Notes

- Everything is deterministic: same seed, same report, every run.
- The dataset is synthetic and invented — no real subjects or trial data.
- No claim is made about any production system; this is a local evaluation
  harness for agentic analytics workflows.
