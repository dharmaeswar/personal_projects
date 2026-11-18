# Agentic Code Migration Evaluator

Benchmarks **AI-assisted code migration**: take legacy Python code, migrate it
(either with an AI coding agent or with the deterministic reference transforms
in this repo), and score the result on behaviour preservation — not on how
modern it looks.

## What it scores

| Check | How |
|---|---|
| Behaviour preservation | Runs fixed test cases against the original and the migrated code in isolated namespaces; outputs must match exactly. |
| Invariants | Public function names must survive; the code must parse and execute; no legacy idiom (`xrange`, `has_key`, `%` formatting, print statements) may remain. |
| Diff quality | Reports lines changed, so a migration that rewrites everything scores worse than a minimal, targeted one. |

Overall score = 0.7 × behaviour + 0.3 × hygiene (hygiene is 1.0 only when every
invariant holds).

## Quick start

```bash
pip install -r requirements.txt
python run_evaluation.py            # benchmark the reference migration
python -m pytest -q                 # run the test suite
```

## Samples

Three legacy modules with known behaviour, in `migration_evaluator/samples.py`:

- `greeting` — `%` string formatting → `.format()` / f-strings
- `counters` — `xrange` → `range`
- `lookup` — `dict.has_key` → `in`, `.format()` string building

## Evaluating your own migration

```python
from migration_evaluator.evaluator import MigrationEvaluator
from migration_evaluator.samples import SAMPLES

sample = SAMPLES["greeting"]
report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
    migrated_source, sample.name
)
print(report.overall_score, report.passed_cases, "/", report.total_cases)
print(report.invariant_failures)
```

## Layout

- `migration_evaluator/transforms.py` — deterministic legacy → modern Python transforms (the reference migration)
- `migration_evaluator/evaluator.py` — `MigrationEvaluator`, executes both versions and scores them
- `migration_evaluator/samples.py` — legacy code samples with expected outputs
- `run_evaluation.py` — CLI benchmark runner
- `tests/` — pytest suite (transforms, evaluator, samples, CLI)

## Why this exists

AI coding tools migrate code fast, but a migration that looks clean and still
changes behaviour is worse than no migration. This evaluator gives teams a
repeatable, execution-based score for every migration an agent produces, so
bad migrations are caught before they reach review.
