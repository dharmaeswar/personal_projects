import pytest

from session_stream.pipeline import (
    Dag, Task, databricks_workflow_job, run_pipeline,
)


def test_dag_runs_in_dependency_order():
    order = []

    def a(ctx):
        order.append("a")
        return {"v": 1}

    def b(ctx):
        order.append("b")
        assert ctx["a"]["v"] == 1
        return {"v": 2}

    dag = Dag("t", tasks=[Task("b", b, depends_on=["a"]), Task("a", a)])
    result = dag.run()
    assert order == ["a", "b"]
    assert result["tasks"]["a"]["status"] == "success"


def test_dag_retries_then_succeeds():
    calls = {"n": 0}

    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("transient")
        return {"ok": True}

    dag = Dag("t", tasks=[Task("flaky", flaky, retries=1)])
    result = dag.run()
    assert result["tasks"]["flaky"]["status"] == "success"
    assert result["tasks"]["flaky"]["attempt"] == 2


def test_dag_fails_after_retries_exhausted():
    def boom(ctx):
        raise ValueError("always broken")

    dag = Dag("t", tasks=[Task("boom", boom, retries=1)])
    with pytest.raises(RuntimeError, match="boom failed"):
        dag.run()


def test_dag_unmet_dependency_raises():
    dag = Dag("t", tasks=[Task("b", lambda ctx: {}, depends_on=["missing"])])
    with pytest.raises(RuntimeError, match="unmet dependency"):
        dag.run()


def test_databricks_workflow_job_structure():
    job = databricks_workflow_job("media-session-streaming",
                                  ["ingest", "cleanse", "publish"],
                                  cluster_workers=3)
    assert job["name"] == "media-session-streaming"
    assert len(job["tasks"]) == 3
    assert job["tasks"][1]["depends_on"] == [{"task_key": "ingest"}]
    assert "depends_on" not in job["tasks"][0]
    cluster = job["job_clusters"][0]["new_cluster"]
    assert cluster["num_workers"] == 3
    assert cluster["autoscale"]["max_workers"] == 8
    assert "schedule" in job


def test_databricks_workflow_job_rejects_zero_workers():
    with pytest.raises(ValueError):
        databricks_workflow_job("x", ["a"], cluster_workers=0)


def test_run_pipeline_end_to_end(tmp_path):
    manifest = run_pipeline(n_sessions=10, seed=42, out_dir=tmp_path)
    assert manifest["events_generated"] > 0
    assert manifest["events_good"] == manifest["events_generated"]
    assert manifest["events_quarantined"] == 0
    assert manifest["events_late"] == 0
    assert manifest["sessions"] == 10
    assert manifest["fact_rows"] == 10
    assert manifest["tables_registered"] == 2
    assert manifest["cost_advice"]["recommended_partitions"] > 0
    assert len(manifest["workflow_job"]["tasks"]) == 4
    assert (tmp_path / "bronze").exists()
    assert (tmp_path / "silver").exists()
    assert (tmp_path / "gold").exists()
