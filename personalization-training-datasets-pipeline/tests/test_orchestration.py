import json

import pytest

from personalization_data import orchestration


def test_topological_order_respects_dependencies():
    order = orchestration.topological_order(orchestration.TASKS)
    assert set(order) == {t["name"] for t in orchestration.TASKS}
    assert order.index("ingest_raw_events") < order.index("cleanse_bronze_to_silver")
    assert order.index("build_training_features") < order.index("publish_gold_dataset")
    assert order.index("publish_gold_dataset") < order.index("quality_report")


def test_topological_order_rejects_cycles():
    with pytest.raises(ValueError, match="cycle"):
        orchestration.topological_order([
            {"name": "a", "depends_on": ["b"]},
            {"name": "b", "depends_on": ["a"]},
        ])


def test_dag_run_success_and_retry():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure")

    run = orchestration.DagRun(orchestration.TASKS, {
        "ingest_raw_events": flaky,
        "cleanse_bronze_to_silver": lambda: None,
        "build_training_features": lambda: None,
        "build_star_schema": lambda: None,
        "publish_gold_dataset": lambda: None,
        "quality_report": lambda: None,
    })
    results = run.run()
    assert results["ingest_raw_events"] == "success"
    assert calls["n"] == 2  # failed once, succeeded on retry
    assert all(v == "success" for v in results.values())


def test_dag_run_skips_downstream_on_failure():
    run = orchestration.DagRun(orchestration.TASKS, {
        "ingest_raw_events": lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        "cleanse_bronze_to_silver": lambda: None,
        "build_training_features": lambda: None,
        "build_star_schema": lambda: None,
        "publish_gold_dataset": lambda: None,
        "quality_report": lambda: None,
    })
    results = run.run()
    assert results["ingest_raw_events"] == "failed"
    assert results["cleanse_bronze_to_silver"] == "skipped"
    assert results["quality_report"] == "skipped"


def test_databricks_spec_and_glue_catalog_are_json_serialisable():
    spec = orchestration.databricks_job_spec()
    assert len(spec["tasks"]) == len(orchestration.TASKS)
    assert spec["schedule"]["quartz_cron_expression"] == "0 2 * * *"
    catalog = orchestration.glue_catalog()
    assert set(catalog["tables"]) == {"bronze_events", "silver_events", "gold_training_dataset"}
    json.dumps(spec)
    json.dumps(catalog)
    json.loads(orchestration.dag_as_json())
