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

## Catalog quality — new, Nov 2026

The same validation pattern, applied to a product catalog the way a
catalog-services team works: normalize product attributes, detect catalog
defects, learn from seller feedback and customer signals, and gate
automated corrections behind an evaluation guardrail.

```bash
python3 run_catalog_quality.py
```

This builds a synthetic 18-product catalog, normalizes every listing,
runs the defect checks, feeds seller feedback into the self-learning
loop, applies only the auto-corrections whose rule is trusted, and
scores the corrections against known-correct values. It writes
`catalog_quality_report.json` and `catalog_quality_report.txt` and
exits `1` when the defect gate fails — the catalog plants nine defects
on purpose, so the committed report shows a `FAIL` gate, 8 corrections
applied, 2 blocked, and the evaluation guardrail `PASS` at precision
0.900. That is the pipeline working as designed, not a bug.

### What it does

- **Normalization** (`eval_quality/catalog.py`) — title whitespace and
  casing, brand-alias lookup (`nike inc.` → `Nike`), price parsing
  (`$12.99`, `1,299.99 USD`), and weight conversion (`12 oz` → 340.19 g).
- **Defect checks** — missing title/brand/category/price and missing
  required attributes per category; zero or unparseable prices, prices
  over 5x the category median, non-USD currency, title naming a
  different brand than the brand field; duplicate listings matched on
  normalized brand, title and key attributes.
- **Self-learning loop** (`FeedbackLoop`) — every seller verdict on a
  proposed correction updates that rule's trust weight
  (accepted + 1) / (total + 2); a rule may auto-correct only once its
  weight reaches 0.80 with at least 3 observations. Customer signals
  (e.g. repeated `wrong-size-report`) flag listings for re-check.
  On the demo data the brand-alias rule is trusted (0.833) and the
  price-outlier rule is not (0.429), so its corrections are blocked.
- **Evaluation guardrail** — proposed corrections are scored against
  known-correct values; the rollout is blocked when precision falls
  below 0.90. Demo: 9 of 10 correct, precision 0.900, guardrail PASS.

### Tests

```bash
python3 -m pytest tests/ -q
```

46 tests, all passing (24 for the eval-dataset pipeline, 22 for the
catalog module).

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
- `eval_quality/catalog.py` — catalog normalization, defect checks, self-learning feedback loop, evaluation guardrail
- `eval_quality/catalog_samples.py` — deterministic synthetic product catalog, feedback events and labeled corrections
- `run_quality_check.py` — CLI entry point
- `run_catalog_quality.py` — CLI entry point for the catalog pipeline
- `tests/` — pytest suites for the checks and the end-to-end pipeline
- `quality_report.json`, `quality_report.txt` — report from the last run
- `catalog_quality_report.json`, `catalog_quality_report.txt` — catalog report from the last run
