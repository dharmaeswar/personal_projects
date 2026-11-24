from datetime import date

from workflow_platform.catalog import Catalog, Connector, Dataset
from workflow_platform.dags import Dag, Task, TenantRegistry
from workflow_platform.diagnostics import diagnose
from workflow_platform.k8s import namespace_for, pod_spec, resource_quota
from workflow_platform.scheduler import TenantQuota, plan_backfill, plan_run, retry_schedule


def sample_dag(tenant="ml"):
    return Dag("pipe", tenant, "0 6 * * *", [
        Task("a", "img", ["run"], outputs=["s.t.a"]),
        Task("b", "img", ["run"], upstream=["a"], inputs=["s.t.a"], outputs=["s.t.b"]),
        Task("c", "img", ["run"], upstream=["b"], inputs=["s.t.b"]),
    ])


def test_topo_order():
    assert sample_dag().topo_order() == ["a", "b", "c"]


def test_cycle_detected():
    dag = Dag("bad", "t", "* * * * *", [
        Task("a", "i", ["r"], upstream=["b"]),
        Task("b", "i", ["r"], upstream=["a"]),
    ])
    assert any("cycle" in p for p in dag.validate())


def test_unknown_upstream_detected():
    dag = Dag("bad", "t", "* * * * *", [Task("a", "i", ["r"], upstream=["ghost"])])
    assert any("unknown task" in p for p in dag.validate())


def test_registry_isolates_tenants():
    reg = TenantRegistry()
    assert reg.register(sample_dag("ml")) == []
    assert reg.register(sample_dag("analytics")) == []
    assert reg.get("ml", "pipe") is not None
    assert reg.get("analytics", "pipe") is not None
    assert reg.list_for_tenant("ml") == ["pipe"]
    assert reg.get("ml", "missing") is None


def test_registry_rejects_invalid_dag():
    reg = TenantRegistry()
    bad = Dag("bad", "t", "* * * * *", [Task("a", "i", ["r"], upstream=["ghost"])])
    assert reg.register(bad) != []
    assert reg.list_for_tenant("t") == []


def test_plan_run_quota_blocks_overflow():
    quota = TenantQuota("ml", max_concurrent_tasks=2, max_runs_per_day=5)
    plan = plan_run(sample_dag(), date(2026, 11, 24), quota)
    states = {t.task_id: t.state for t in plan.task_runs}
    assert states["a"] == "queued"
    assert states["c"] == "quota_blocked"
    assert plan.blocked_tasks() == ["c"]


def test_plan_run_counts_already_running():
    quota = TenantQuota("ml", max_concurrent_tasks=2, max_runs_per_day=5)
    plan = plan_run(sample_dag(), date(2026, 11, 24), quota, already_running=2)
    assert plan.blocked_tasks() == ["a", "b", "c"]


def test_backfill_one_plan_per_day():
    quota = TenantQuota("ml", max_concurrent_tasks=9, max_runs_per_day=5)
    plans = plan_backfill(sample_dag(), date(2026, 11, 20), date(2026, 11, 22), quota)
    assert [p.logical_date.day for p in plans] == [20, 21, 22]


def test_retry_schedule_backoff_and_cap():
    assert retry_schedule(3, base_delay_seconds=60) == [60, 120, 240]
    assert retry_schedule(6, base_delay_seconds=600)[-1] == 1800


def test_pod_spec_shape():
    dag = sample_dag()
    spec = pod_spec(dag, dag.task_map()["b"], "2026-11-24", 2)
    assert spec["metadata"]["namespace"] == "wf-ml"
    assert spec["metadata"]["labels"]["task_id"] == "b"
    env = {e["name"]: e["value"] for e in spec["spec"]["containers"][0]["env"]}
    assert env["LOGICAL_DATE"] == "2026-11-24"
    assert namespace_for("ml") == "wf-ml"


def test_resource_quota():
    q = resource_quota("ml", 20, "10", "20Gi")
    assert q["spec"]["hard"]["pods"] == "20"
    assert q["metadata"]["namespace"] == "wf-ml"


def test_catalog_lineage_and_impact():
    cat = Catalog()
    cat.register(Dataset("s.t.a", "snowflake", "ml"))
    cat.register(Dataset("s.t.b", "snowflake", "ml"))
    cat.ingest_dag_lineage(sample_dag())
    assert cat.upstream_of("s.t.b") == ["s.t.a"]
    assert cat.downstream_of("s.t.a") == ["s.t.b"]
    assert cat.impact_of("s.t.a") == ["s.t.b"]


def test_catalog_search_and_connector():
    cat = Catalog()
    n = Connector("postgres").ingest(cat, "ml", {"events": ["id"], "users": ["id"]})
    assert n == 2
    assert cat.get("postgres.ml.events") is not None
    assert cat.search("events") == ["postgres.ml.events"]


def test_diagnose_oom():
    d = diagnose(137, "OOMKilled", {})
    assert d.category == "out_of_memory" and d.retry_worth_it


def test_diagnose_upstream_first():
    d = diagnose(1, "OOMKilled", {"a": "failed"})
    assert d.category == "upstream_failure" and not d.retry_worth_it


def test_diagnose_permissions_no_retry():
    d = diagnose(1, "Access denied for user", {})
    assert d.category == "permissions" and not d.retry_worth_it


def test_diagnose_timeout_and_connectivity():
    assert diagnose(1, "request timed out", {}).category == "timeout"
    assert diagnose(1, "connection refused", {}).category == "connectivity"
