# ML Training & Serving Platform

A small, self-contained platform for training, registering, and serving a
credit-decision model — the kind of infrastructure an ML Training & Serving
team runs: a versioned model registry, an offline training pipeline with a
backfill job, and a serving layer with canary rollout, latency/throughput
tracking, drift checks, and rollback.

**All data in this project is synthetic.** No real customer, credit, or
Affirm data is used anywhere. Features and labels are generated with a
seeded random generator so every run is reproducible.

## What it does

- **Training pipeline** (`ml_platform/training.py`): generates a synthetic
  credit-application dataset (income, debt ratio, credit history length,
  delinquencies, requested amount), trains a logistic-regression model with
  plain-Python gradient descent, and reports accuracy, precision, recall,
  and AUC on a held-out split.
- **Model registry** (`ml_platform/registry.py`): stores versioned models
  with metadata (metrics, training date, feature list, stage) in a JSON
  file, and promotes models through `staging` -> `production` ->
  `archived`. Only one model version is production at a time.
- **Serving API** (`ml_platform/serving.py`): scores applications against
  the production model, with a canary rollout that sends a configurable
  share of traffic to a candidate version, per-request latency tracking,
  and a drift check that compares recent feature distributions with the
  training baseline (population stability index). If drift or error rate
  crosses a threshold, `rollback()` restores the previous production
  version.
- **Offline backfill** (`ml_platform/backfill.py`): re-scores a batch of
  historical applications with a given model version and writes the
  predictions to a CSV, so a new version can be compared with the old one
  before it is promoted.
- **Next-best-action decisioning** (`ml_platform/decisioning.py`): scores
  a small set of candidate actions (care-gap reminder, preventive
  screening nudge, wellness program invite, benefits explanation) for a
  member using the production model, applies simple eligibility and
  business rules (suppress an action already completed, suppress a
  screening nudge when the member was recently screened, cap contacts
  per member per week), picks the best eligible action, and logs each
  decision (timestamp, member, chosen action, scores, model version,
  rules applied) to a JSONL file. An outcome report joins logged
  decisions with supplied outcomes and compares the model-chosen
  decisions against a rule-only baseline (fixed priority order, no
  model scores). This is model-score + business-rule decisioning only —
  it is not reinforcement learning, bandit optimisation, or any other
  adaptive policy. All member data is synthetic, seeded, and
  reproducible; no real member or Humana data is used.

## Layout

```
ml-training-serving-platform/
  README.md
  requirements.txt          # stdlib only; pytest for tests
  run_demo.py               # end-to-end demo: train -> register -> serve -> canary -> rollback
  ml_platform/
    __init__.py
    data.py                 # synthetic dataset generation
    training.py             # logistic regression trainer + metrics
    registry.py             # versioned model registry (JSON-backed)
    serving.py              # prediction service, canary, drift, rollback
    backfill.py             # offline batch re-scoring
    decisioning.py          # next-best-action decisioning + outcome tracking
  tests/
    test_data.py
    test_training.py
    test_registry.py
    test_serving.py
    test_backfill.py
    test_decisioning.py
```

## Run it

```bash
python3 run_demo.py            # full end-to-end demo (incl. decisioning)
python3 -m pytest -q           # test suite
```

## Design notes

- No external dependencies for the platform itself — the model is plain
  Python so the training, registry, and serving code can be read and run
  anywhere. Only `pytest` is needed for tests.
- The registry is the single source of truth for which version serves
  traffic; the serving layer never hard-codes a version.
- Canary rollout is deterministic per application id (hash-based), so the
  same application always hits the same version during a rollout.
- Drift is checked with PSI on each feature; a feature with PSI above
  0.25 is flagged, and the service exposes it so an operator can decide
  whether to roll back or retrain.
