# Autonomy Evaluation & Metrics Platform

A portfolio project for the **Rivian — Senior Software Engineer, Autonomy Evaluation & Metrics Platform** application (job 35827, Palo Alto, CA). It models the platform behind Rivian's Autonomy Eval Infrastructure team: a metrics platform that makes autonomy evaluation consistent and reproducible, connecting model development with evaluation workflows, metrics, triage, and visualization across simulation and real-world vehicle data.

**All data is synthetic.** No real Rivian data, models, vehicles, or driving measurements are used, and nothing here describes a real Rivian system. There is no live Spark, Databricks, Delta Lake, or AWS: the registry, computation, comparison, and gating logic are plain Python so the platform behavior can be tested end to end.

## Problem statement

When one platform evaluates many models, the platform team has to solve problems no single model team sees:

- **Versioned metric definitions** — a metric's definition must never silently change under old results, or a "regression" may just be a redefinition.
- **Provenance** — every official run is pinned to code, model, dataset, and scenario versions, so two runs are only compared when their inputs match.
- **Idempotent, incremental computation** — retries and duplicate deliveries must not double-count; new data should recompute only the affected slices; backfills must be visible as backfills.
- **Honest comparisons** — a point-estimate move inside the noise is inconclusive, not a regression; sample sizes, coverage, and uncertainty travel with every number.
- **Regression vs. data vs. infra** — a moved metric with dropped coverage or failed jobs is a data or infrastructure problem, not a model regression.
- **Release gates** — thresholds per metric turn comparisons into a pass/fail release decision a release team can act on, wired into CI.

## What is inside

```
eval_platform/
  registry.py     Versioned metric definitions (register, get, deprecate)
  provenance.py   EvalRun provenance + RunLedger (comparability rules)
  compute.py      Idempotent metric computation, incremental slices, backfills
  compare.py      Wilson/mean confidence intervals, regression verdicts,
                  failure classification (model vs data vs infra)
  gates.py        Regression gates + release evidence report
  service.py      Service API + CI hook (ci_check)
run_demo.py       End-to-end demo: two model versions, compare, gate, diagnose
tests/            Pytest suite covering every module
```

## Run it

```bash
python3 run_demo.py
python3 -m pytest -q
```

## Example

```python
from eval_platform import EvalMetricsPlatform
from eval_platform.gates import Gate
from eval_platform.provenance import EvalRun

p = EvalMetricsPlatform()
p.register_metric("intervention_rate", "Safety-critical interventions",
                  "rate", "rate", higher_is_better=False)
p.add_gate(Gate("intervention_rate", max_regression=0.005, higher_is_better=False))
p.record_run(EvalRun("run-1", "intervention_rate", 1, "code-a1",
                     "model-2026.11", "dataset-2026.10", "scenarios-v12", "simulation"))
p.compute_metric("run-1", "intervention_rate", "highway",
                 [1.0] * 9 + [0.0] * 991, expected_scenarios=1000)
comparison = p.compare_models("intervention_rate", 12, 1000, 9, 1000)
print(p.ci_check("model-2026.11", {"intervention_rate": comparison}))
```

## Honest limits

- In-memory only; no Spark/Databricks/Delta Lake, no AWS, no Docker/GitLab CI — the distributed computation and storage paths the real role builds are modeled as module boundaries, not run here.
- Single-process, single-node: no distributed execution, no real replay or closed-loop simulation — the evaluation data is seeded lists, not vehicle or simulator output.
- Statistics are Wilson intervals for rates and normal-approximation intervals for means; no Bayesian or bootstrap analysis, and no domain-expert review step.
- Demonstrated on seeded synthetic scenarios, not at production scale.
