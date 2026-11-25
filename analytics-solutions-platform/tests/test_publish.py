import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.publish import publish_dataset, read_latest_manifest


def test_publish_writes_partition_and_manifest(tmp_path):
    rows = [{"policy_id": "P1", "premium_annual": 100.0},
            {"policy_id": "P2", "premium_annual": 200.0}]
    manifest = publish_dataset(rows, "policy_activity_dashboard", str(tmp_path),
                               date(2026, 11, 20), schema=["policy_id", "premium_annual"],
                               gate_passed=True, metric_versions={"active_policies": "v1"})
    assert manifest["row_count"] == 2
    assert manifest["quality_gate_passed"] is True
    assert manifest["metric_versions"] == {"active_policies": "v1"}
    assert os.path.exists(manifest["path"])
    back = read_latest_manifest(str(tmp_path), "policy_activity_dashboard")
    assert back == manifest


def test_latest_manifest_wins_across_partitions(tmp_path):
    publish_dataset([{"a": 1}], "ds", str(tmp_path), date(2026, 11, 19),
                    schema=["a"], gate_passed=True, metric_versions={})
    publish_dataset([{"a": 1}, {"a": 2}], "ds", str(tmp_path), date(2026, 11, 20),
                    schema=["a"], gate_passed=True, metric_versions={})
    latest = read_latest_manifest(str(tmp_path), "ds")
    assert latest["partition"] == "date=2026-11-20"
    assert latest["row_count"] == 2
