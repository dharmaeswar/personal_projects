# Employee Experience Science

Statistical analysis of employee experience: which groups of employees
have a measurably worse experience, and by how much — with the
statistics to back every claim. Built for a People Experience and
Technology (PXT) Central Science style problem: translate a business
question ("where are the experience defects?") into a rigorous
quantitative framework, test it, and communicate the result.

All data is synthetic (1,200 employees, fixed seed) and all statistics
are implemented from scratch in the standard library — no SciPy.

## The problem

A company with 1M+ employees cannot fix every complaint. It needs to
know which segments (shift, overtime, manager tenure, schedule
stability, tenure) are *significantly* worse, how large the gap is, and
whether those employees also leave at higher rates — before spending
money on a fix.

## What it does

1. **Generates** a deterministic synthetic workforce (`experience_science/data.py`):
   organisation, shift, tenure, manager tenure, weekly overtime,
   monthly schedule changes, experience and wellbeing scores (1–5),
   an attrition flag, and one open-ended feedback comment with a known
   true theme. Effects are planted on purpose (night shift, overtime,
   new managers, unstable schedules) so the analysis is checkable.
2. **Finds experience defects** (`experience_science/defects.py`):
   five pre-registered segment comparisons on experience score with
   Welch's t-test, bootstrap 95% confidence intervals, Cohen's d, and
   a chi-square test on attrition rates — with a Bonferroni correction
   across all five comparisons.
3. **Benchmarks feedback-theme classification** (`experience_science/feedback.py`):
   a transparent keyword classifier for open-ended comments, scored
   against true themes with per-theme precision/recall/F1 and macro F1.
   This is the baseline a GenAI feedback summariser must beat.
4. **Writes a plain-language report** (`experience_science/report.py`)
   that a non-technical audience can act on.
5. **Forecasts workforce needs** (`experience_science/forecast.py`,
   added Nov 2026 for a workforce-planning data-science role): a
   logistic-regression attrition-risk model on overtime, shift,
   schedule churn, manager tenure, tenure and experience score, scored
   on a held-out split (AUC, Brier vs base rate, quintile calibration);
   plus a 12-month monthly attrition history simulated from each org's
   observed annual attrition rate with a seasonal pattern, a trend
   forecast with 95% prediction intervals, and a backtest that fits on
   months 1–9 and scores months 10–12 before the forecast is trusted.

## Run it

```bash
pip install -r requirements.txt
python run_analysis.py        # prints the report, writes experience_report.txt
python -m pytest -q           # 22 tests
```

## What the data shows (1,200 synthetic employees, seed fixed)

| Segment | Experience gap | Attrition |
| --- | --- | --- |
| Night vs Day shift | −0.56 points (Cohen's d −0.89) | 16.8% vs 9.3% |
| Overtime >10h vs ≤10h | −0.54 points (Cohen's d −0.82) | 22.8% vs 9.7% |
| New manager (<1y) vs experienced | −0.38 points (Cohen's d −0.56) | 13.3% vs 11.3% |
| 4+ schedule changes vs fewer | −0.26 points (Cohen's d −0.39) | 19.6% vs 10.3% |

Exact numbers are in `experience_report.txt` after a run; every
confirmed defect survives the Bonferroni correction (4 of 5 segments
tested; short tenure shows no real gap). The feedback classifier
scores accuracy 0.882 and macro F1 0.931 on the six themes
(workload, schedule, manager, pay, growth, tools) — vague comments
with no theme keywords are its misses, which is exactly the gap a
GenAI summariser would need to close.

## Workforce-planning forecasts (12-month simulated history, seed fixed)

- Attrition-risk model, held-out n=240: AUC 0.724, Brier 0.1317 vs
  base-rate 0.1431 (base attrition rate 10.2%). Strongest drivers:
  experience score −0.714, overtime +0.230 standardised coefficients.
- Calibration is honest about its limit: the top risk quintile is
  under-predicted (predicted 0.206 vs observed 0.375) — attrition jumps
  at low experience scores, a threshold effect a linear logit only
  partly captures. Schedule churn's effect is mediated through the
  experience score, not direct.
- Headcount forecast backtest (fit months 1–9, scored 10–12): MAPE
  32.0%, 95% interval coverage 100% (3 of 3 months inside). Next
  quarter forecast: ~9, ~9 and ~8 attritions per month, each with a
  wide 95% interval (±7) — small monthly counts are noisy, and the
  intervals say so.

## Limits

Synthetic data, planted effects, and a rule-based classifier baseline —
this is a local analysis pipeline, not production HR data and not a
claim about any real workforce. No employee data is used. The monthly
attrition history is simulated from the observed annual rate (divided
by 12) at steady headcount with replacement hiring, so its absolute
counts are illustrative; what the backtest validates is the
forecasting method, not a real headcount plan.
