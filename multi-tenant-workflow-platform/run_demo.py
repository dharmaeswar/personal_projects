"""End-to-end demo with synthetic tenants, DAGs, and datasets.

Run: python run_demo.py
"""
from datetime import date

from workflow_platform.catalog import Catalog, Connector
from workflow_platform.dags import Dag, Task, TenantRegistry
from workflow_platform.diagnostics import diagnose
from workflow_platform.k8s import pod_spec
from workflow_platform.scheduler import TenantQuota, plan_backfill, plan_run


def build_demo() -> None:
    registry = TenantRegistry()
    ml_dag = Dag(
        dag_id="ml_feature_pipeline",
        tenant="ml-platform",
        schedule="0 6 * * *",
        tasks=[
            Task("extract_events", "python:3.12", ["python", "extract.py"],
                 outputs=["postgres.ml.raw_events"]),
            Task("build_features", "python:3.12", ["python", "features.py"],
                 upstream=["extract_events"],
                 inputs=["postgres.ml.raw_events"],
                 outputs=["snowflake.ml.feature_store"]),
            Task("train_model", "python:3.12", ["python", "train.py"],
                 upstream=["build_features"],
                 inputs=["snowflake.ml.feature_store"]),
        ],
    )
    analytics_dag = Dag(
        dag_id="daily_sessions",
        tenant="analytics",
        schedule="0 7 * * *",
        tasks=[
            Task("load_sessions", "python:3.12", ["python", "load.py"],
                 outputs=["snowflake.analytics.daily_sessions"]),
        ],
    )
    for dag in (ml_dag, analytics_dag):
        problems = registry.register(dag)
        assert not problems, problems
    print("tenants:", registry.tenants())

    quota = TenantQuota(tenant="ml-platform", max_concurrent_tasks=2, max_runs_per_day=3)
    plan = plan_run(ml_dag, date(2026, 11, 24), quota)
    print("run plan:", [(t.task_id, t.state) for t in plan.task_runs])
    print("quota-blocked:", plan.blocked_tasks())
    backfill = plan_backfill(ml_dag, date(2026, 11, 20), date(2026, 11, 22), quota)
    print("backfill runs:", len(backfill))

    spec = pod_spec(ml_dag, ml_dag.task_map()["build_features"], "2026-11-24", 1)
    print("pod:", spec["metadata"]["name"], "in namespace", spec["metadata"]["namespace"])

    catalog = Catalog()
    Connector("postgres").ingest(catalog, "ml", {"raw_events": ["event_id", "ts", "user_id"]})
    Connector("snowflake").ingest(catalog, "ml", {"feature_store": ["user_id", "f1", "f2"]})
    Connector("snowflake").ingest(catalog, "analytics", {"daily_sessions": ["day", "sessions"]})
    catalog.ingest_dag_lineage(ml_dag)
    print("lineage upstream of feature_store:", catalog.upstream_of("snowflake.ml.feature_store"))
    print("impact of raw_events:", catalog.impact_of("postgres.ml.raw_events"))

    diag = diagnose(137, "container OOMKilled", {"extract_events": "success"})
    print("diagnosis:", diag.category, "-", diag.suggested_action)


if __name__ == "__main__":
    build_demo()
