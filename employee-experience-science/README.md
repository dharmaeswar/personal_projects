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

## Run it

```bash
pip install -r requirements.txt
python run_analysis.py        # prints the report, writes experience_report.txt
python -m pytest -q           # 15 tests
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

## Limits

Synthetic data, planted effects, and a rule-based classifier baseline —
this is a local analysis pipeline, not production HR data and not a
claim about any real workforce. No employee data is used.
