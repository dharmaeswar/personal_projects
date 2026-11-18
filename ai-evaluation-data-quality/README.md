# AI Evaluation Data Quality

A Python pipeline that validates AI evaluation datasets for a trust & safety
team before the data is used to score a model. It checks that every
prompt/response pair is complete, that labels follow the harm taxonomy, that
every harm category has enough eval coverage, that no prompt leaks between
the train and eval splits, and that no personal data (PII) slipped into the
text. It then writes a quality report with a pass/fail gate.

Plain Python (standard library only, plus pytest for tests). No Spark, Glue,
EMR, Redshift or other production data-platform use is claimed — this is a
local validation pipeline over JSON-like records.

## Checks

| Check | What it catches |
| --- | --- |
| `completeness` | Missing ids, duplicate ids, empty prompts or responses |
| `label-consistency` | Labels outside the harm taxonomy; records labelled `safe` that contain disallowed content |
| `coverage` | Harm categories with fewer than the minimum eval records (default 3) |
| `leakage` | The same prompt in both train and eval splits, or duplicated inside one split |
| `pii-scan` | Email, phone, SSN and credit-card-like patterns in prompts or responses |

Harm taxonomy: `violence`, `self-harm`, `hate`, `sexual-content`,
`illicit-behavior`, `safe`.

## Run it

```bash
python3 run_quality_check.py
```

This builds the synthetic corpus, runs every check, prints the report and
writes `quality_report.json` and `quality_report.txt`. It exits `1` when the
quality gate fails (any critical finding), so it can sit in a CI step.

## Tests

```bash
python3 -m pytest tests/ -q
```

24 tests, all passing.

## The synthetic corpus

`eval_quality/samples.py` builds a deterministic 52-record corpus (36 train,
16 eval) from invented prompts — no real user data. Six quality problems are
planted on purpose so the pipeline has real defects to catch:

1. `eval-001` has an empty response (completeness).
2. `train-002` carries the label `unknown-category` (label consistency).
3. `train-003` is labelled `safe` but its response holds a disallowed phrase.
4. The prompt of `train-007` also appears as `eval-004` (train/eval leakage).
5. `eval-005` has a personal email address in its response (PII scan).
6. `self-harm` has only 1 record in the eval split (coverage).

The committed report therefore shows 6 findings (5 critical, 1 warning) and
a `FAIL` gate — that is the pipeline working as designed, not a bug.

## Layout

- `eval_quality/checks.py` — the five checks and `run_all_checks()`
- `eval_quality/samples.py` — deterministic synthetic corpus generator
- `eval_quality/report.py` — text and JSON report rendering
- `run_quality_check.py` — CLI entry point
- `tests/` — pytest suites for the checks and the end-to-end pipeline
- `quality_report.json`, `quality_report.txt` — report from the last run
