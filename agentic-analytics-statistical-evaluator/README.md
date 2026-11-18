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
python -m pytest -q          # 19 tests
```

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

- `agentic_stats/stats.py` — t-test, chi-square, bootstrap CI, Cohen's d,
  Bonferroni, power, interaction test (pure stdlib)
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
