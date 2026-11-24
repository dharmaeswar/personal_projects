"""Tests for ops/fleet_systems.py — synthetic Linux fleet data only."""

from ops.fleet_systems import (
    CANARY_FRACTION,
    check_drift,
    fleet_drift_report,
    fleet_summary,
    host_is_healthy,
    make_host,
    run_rollout,
    stage_hosts,
)


def _hosts():
    return [
        make_host("dc1-compute-01", "compute", "Ubuntu 22.04", "5.15.0-91",
                  {"python3": "3.10.12", "openssh-server": "8.9p1"},
                  {"sshd": True, "node-exporter": True}),
        make_host("dc1-compute-02", "compute", "Ubuntu 22.04", "5.15.0-91",
                  {"python3": "3.10.12", "openssh-server": "8.9p1"},
                  {"sshd": True, "node-exporter": True}),
        make_host("dc1-storage-01", "storage", "Ubuntu 22.04", "5.15.0-88",
                  {"python3": "3.10.12", "openssh-server": "8.9p1"},
                  {"sshd": True, "node-exporter": False}),
        make_host("dc1-network-01", "network", "Ubuntu 20.04", "5.4.0-150",
                  {"python3": "3.8.10", "openssh-server": "8.9p1"},
                  {"sshd": True, "node-exporter": True}, cpu_count=4),
    ]


def _desired():
    return {"os_version": "Ubuntu 22.04", "kernel": "5.15.0-91",
            "packages": {"python3": "3.10.12"},
            "services": {"sshd": True, "node-exporter": True}}


def test_make_host_defaults():
    host = make_host("h1", "compute", "Ubuntu 22.04", "5.15.0-91")
    assert host["packages"] == {}
    assert host["services"] == {}
    assert host["status"] == "healthy"
    assert host["cpu_count"] == 8


def test_check_drift_clean_host():
    assert check_drift(_hosts()[0], _desired()) == []


def test_check_drift_reports_kernel_package_service():
    drift = check_drift(_hosts()[2], _desired())
    fields = {d["field"] for d in drift}
    assert fields == {"kernel", "service:node-exporter"}
    kernel = [d for d in drift if d["field"] == "kernel"][0]
    assert kernel["expected"] == "5.15.0-91"
    assert kernel["actual"] == "5.15.0-88"


def test_check_drift_missing_package_counts_as_drift():
    host = make_host("h1", "compute", "Ubuntu 22.04", "5.15.0-91",
                     {"openssh-server": "8.9p1"}, {"sshd": True})
    drift = check_drift(host, _desired())
    pkg = [d for d in drift if d["field"] == "package:python3"][0]
    assert pkg["actual"] is None
    assert pkg["expected"] == "3.10.12"


def test_fleet_drift_report_totals():
    report = fleet_drift_report(_hosts(), _desired())
    assert report["hosts_checked"] == 4
    assert report["hosts_with_drift"] == 2
    assert report["total_drift"] == 5
    assert report["worst_hosts"][0] == "dc1-network-01"


def test_stage_hosts_canary_first_and_covers_all():
    stages = stage_hosts(_hosts())
    assert stages[0] == ["dc1-compute-01"]
    flat = [name for stage in stages for name in stage]
    assert sorted(flat) == sorted(h["hostname"] for h in _hosts())
    assert len(flat) == len(set(flat))


def test_stage_hosts_single_host_one_stage():
    stages = stage_hosts(_hosts()[:1])
    assert stages == [["dc1-compute-01"]]


def test_stage_hosts_empty_fleet():
    assert stage_hosts([]) == []


def test_host_is_healthy_limits():
    host = _hosts()[0]
    assert host_is_healthy(host, {"cpu_util_pct": 40, "mem_used_pct": 50})
    assert not host_is_healthy(host, {"cpu_util_pct": 90, "mem_used_pct": 50})
    assert not host_is_healthy(host, {"cpu_util_pct": 40, "mem_used_pct": 95})
    assert not host_is_healthy(
        make_host("h9", "compute", "Ubuntu 22.04", "5.15.0-91",
                  status="degraded"),
        {"cpu_util_pct": 10, "mem_used_pct": 10})


def test_rollout_completes_when_all_healthy():
    hosts = _hosts()
    applied = []
    signals = {h["hostname"]: {"cpu_util_pct": 30, "mem_used_pct": 40}
               for h in hosts}
    report = run_rollout(hosts, lambda h: applied.append(h["hostname"]),
                         lambda h: None, signals)
    assert report["status"] == "complete"
    assert report["failed_stage"] is None
    assert sorted(report["applied"]) == sorted(applied)
    assert report["rolled_back"] == []


def test_rollout_rolls_back_failed_stage_only():
    hosts = _hosts()
    rolled_back = []
    signals = {h["hostname"]: {"cpu_util_pct": 30, "mem_used_pct": 40}
               for h in hosts}
    signals["dc1-compute-02"] = {"cpu_util_pct": 97, "mem_used_pct": 40}
    report = run_rollout(hosts, lambda h: None,
                         lambda h: rolled_back.append(h["hostname"]),
                         signals)
    assert report["status"] == "rolled back"
    assert report["failed_stage"] == 2
    assert report["failed_hosts"] == ["dc1-compute-02"]
    assert report["rolled_back"] == ["dc1-compute-02"]
    assert report["applied"] == ["dc1-compute-01"]


def test_rollout_canary_failure_stops_immediately():
    hosts = _hosts()
    signals = {h["hostname"]: {"cpu_util_pct": 30, "mem_used_pct": 40}
               for h in hosts}
    signals["dc1-compute-01"] = {"cpu_util_pct": 99, "mem_used_pct": 40}
    report = run_rollout(hosts, lambda h: None, lambda h: None, signals)
    assert report["status"] == "rolled back"
    assert report["stages_attempted"] == 1
    assert report["rolled_back"] == ["dc1-compute-01"]


def test_fleet_summary_counts():
    summary = fleet_summary(_hosts())
    assert summary["total_hosts"] == 4
    assert summary["by_role"] == {"compute": 2, "storage": 1, "network": 1}
    assert summary["by_status"] == {"healthy": 4}
    assert summary["unhealthy_hosts"] == []


def test_fleet_summary_flags_unhealthy():
    hosts = _hosts()
    hosts[1]["status"] = "degraded"
    summary = fleet_summary(hosts)
    assert summary["unhealthy_hosts"] == ["dc1-compute-02"]
    assert summary["by_status"]["degraded"] == 1


def test_canary_fraction_is_ten_percent():
    assert CANARY_FRACTION == 0.1
