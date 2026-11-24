"""End-to-end demo of ops/fleet_systems.py on a synthetic 12-host fleet.

Builds a fleet, reports config drift against a desired state, rolls a
change out in stages with one host failing its health gate (so that
stage rolls back), and prints a fleet summary. All data is synthetic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ops.fleet_systems import (  # noqa: E402
    check_drift,
    fleet_drift_report,
    fleet_summary,
    make_host,
    run_rollout,
    stage_hosts,
)

DESIRED = {"os_version": "Ubuntu 22.04", "kernel": "5.15.0-91",
           "packages": {"python3": "3.10.12"},
           "services": {"sshd": True, "node-exporter": True}}


def build_fleet():
    hosts = []
    for i in range(1, 7):
        hosts.append(make_host(f"dc1-compute-{i:02d}", "compute",
                               "Ubuntu 22.04", "5.15.0-91",
                               {"python3": "3.10.12"},
                               {"sshd": True, "node-exporter": True}))
    for i in range(1, 4):
        hosts.append(make_host(f"dc1-storage-{i:02d}", "storage",
                               "Ubuntu 22.04", "5.15.0-91",
                               {"python3": "3.10.12"},
                               {"sshd": True, "node-exporter": True}))
    for i in range(1, 4):
        hosts.append(make_host(f"dc1-network-{i:02d}", "network",
                               "Ubuntu 22.04", "5.15.0-91",
                               {"python3": "3.10.12"},
                               {"sshd": True, "node-exporter": True}))
    # Two hosts drift from the desired state.
    hosts[6]["kernel"] = "5.15.0-88"
    hosts[9]["packages"]["python3"] = "3.8.10"
    return hosts


def main():
    hosts = build_fleet()
    print(f"Fleet: {len(hosts)} hosts")
    print(f"Rollout stages: {stage_hosts(hosts)}")

    report = fleet_drift_report(hosts, DESIRED)
    print(f"Drift: {report['total_drift']} items across "
          f"{report['hosts_with_drift']} hosts; "
          f"worst: {report['worst_hosts']}")
    for entry in report["per_host"]:
        if entry["drift_count"]:
            print(f"  {entry['hostname']}: "
                  + ", ".join(d["field"] for d in entry["drift"]))

    applied = []
    rolled_back = []

    def apply(host):
        applied.append(host["hostname"])

    def rollback(host):
        rolled_back.append(host["hostname"])

    signals = {h["hostname"]: {"cpu_util_pct": 35, "mem_used_pct": 45}
               for h in hosts}
    signals["dc1-compute-03"] = {"cpu_util_pct": 96, "mem_used_pct": 45}
    result = run_rollout(hosts, apply, rollback, signals)
    print(f"Rollout: {result['status']} after "
          f"{result['stages_attempted']} stages; "
          f"applied {len(result['applied'])}, "
          f"rolled back {len(result['rolled_back'])} "
          f"(failed stage {result['failed_stage']}: "
          f"{result['failed_hosts']})")

    print(f"Summary: {fleet_summary(hosts)}")
    print(f"Drift on a clean host: {check_drift(hosts[0], DESIRED)}")


if __name__ == "__main__":
    main()
