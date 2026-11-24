# Multi-Tenant Workflow Platform

A portfolio project for a **Senior Software Developer, Data Platform** role (Rocket Companies / Redfin Data Tooling style). It models the platform layer behind a shared workflow orchestration service — the kind of internal platform that many engineering, analytics, and ML teams depend on to build, schedule, discover, and run data pipelines.

**All data is synthetic.** No real company, tenant, or pipeline data is used, and nothing here is a claim about any real system. There is no live Kubernetes cluster or Airflow install: the pod specs and run plans are generated as data so the platform logic can be tested end to end.

## Problem statement

When one orchestration platform serves many teams, the platform team has to solve problems no single team sees:

- **Tenant isolation** — one team's DAGs, namespaces, and quotas must never leak into or starve another team's.
- **Safe scheduling** — DAGs must be validated (no cycles, no dangling dependencies) before they run, planned in dependency order, backfilled by date, and retried with backoff — all inside the tenant's concurrency and daily-run quotas.
- **Kubernetes execution** — every task run becomes a pod in the tenant's own namespace, with resource requests, labels, and run identity passed as environment.
- **Discovery and lineage** — engineers need one catalog across stores (Postgres, Snowflake, S3, Kafka) that answers "what feeds this dataset, and what breaks if it changes?"
- **Self-service support** — most platform failures are one of a few known patterns (OOM, timeout, connectivity, permissions, schema change, upstream failure). A diagnostics helper classifies a failed run from its exit code and log tail and suggests the fix, so users get an answer before paging the platform team.

## What is inside

```
workflow_platform/
  dags.py         Task/Dag model, validation (cycles, unknown deps), tenant registry
  scheduler.py    Run planning in topo order, backfill planning, retry backoff, quotas
  k8s.py          Pod-spec and ResourceQuota generation per tenant namespace
  catalog.py      Dataset catalog, store connectors, lineage and impact analysis
  diagnostics.py  Failure classification with suggested actions and retry advice
run_demo.py       End-to-end demo: two tenants, run plans, pod spec, lineage, diagnosis
tests/            Pytest suite covering every module
```

## Run it

```bash
python run_demo.py
python -m pytest tests/ -q
```

## Skills used

Only verified skills: Python, Kubernetes concepts, Docker concepts, SQL/data-platform design, testing with Pytest. This project does **not** claim production Airflow, Helm, dbt, or Datadog experience — the orchestration model here is original Python code, and the README says so wherever it matters.
