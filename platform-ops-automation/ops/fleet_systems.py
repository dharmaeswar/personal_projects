"""Linux fleet systems automation for the Platform Ops Automation demo.

Models the systems-development side of running a data-center fleet:
an inventory of Linux hosts, config-drift checks against a desired
state, and staged rollouts with health gates and automatic rollback.

All data is synthetic and local. No real host, fleet, or production
system is described, and no production systems-development experience
is claimed.
"""

CANARY_FRACTION = 0.1
DEFAULT_STAGES = (0.1, 0.5, 1.0)

HEALTH_CPU_MAX_PCT = 85
HEALTH_MEM_MAX_PCT = 90


def make_host(hostname, role, os_version, kernel, packages=None,
              services=None, cpu_count=8, status="healthy"):
    """Build one synthetic Linux host record.

    `packages` maps package name -> installed version string.
    `services` maps service name -> True when running.
    """
    return {
        "hostname": hostname,
        "role": role,
        "os_version": os_version,
        "kernel": kernel,
        "packages": dict(packages or {}),
        "services": dict(services or {}),
        "cpu_count": cpu_count,
        "status": status,
    }


def check_drift(host, desired):
    """Compare one host against the desired state.

    `desired` may set `os_version`, `kernel`, `packages` (name ->
    required version) and `services` (name -> True when it must run).
    Returns a list of drift dicts with `field`, `expected`, `actual`.
    """
    drift = []
    for field in ("os_version", "kernel"):
        if field in desired and host.get(field) != desired[field]:
            drift.append({"field": field, "expected": desired[field],
                          "actual": host.get(field)})
    for name, version in desired.get("packages", {}).items():
        actual = host.get("packages", {}).get(name)
        if actual != version:
            drift.append({"field": f"package:{name}", "expected": version,
                          "actual": actual})
    for name, must_run in desired.get("services", {}).items():
        actual = host.get("services", {}).get(name, False)
        if bool(actual) != bool(must_run):
            drift.append({"field": f"service:{name}",
                          "expected": "running" if must_run else "stopped",
                          "actual": "running" if actual else "stopped"})
    return drift


def fleet_drift_report(hosts, desired):
    """Per-host drift counts plus a fleet total and the worst hosts."""
    per_host = []
    total = 0
    for host in hosts:
        items = check_drift(host, desired)
        total += len(items)
        per_host.append({"hostname": host["hostname"], "role": host["role"],
                         "drift_count": len(items), "drift": items})
    worst = sorted(per_host, key=lambda h: -h["drift_count"])
    return {"hosts_checked": len(hosts), "total_drift": total,
            "hosts_with_drift": sum(1 for h in per_host if h["drift_count"]),
            "per_host": per_host,
            "worst_hosts": [h["hostname"] for h in worst[:3]
                            if h["drift_count"]]}


def stage_hosts(hosts, stage_fractions=DEFAULT_STAGES):
    """Split hosts into rollout stages: canary, then growing fractions.

    Each stage is a list of hostnames. Fractions are cumulative, so
    (0.1, 0.5, 1.0) rolls out to 10%, then 50%, then all hosts.
    Every host appears in exactly one stage.
    """
    ordered = sorted(hosts, key=lambda h: h["hostname"])
    total = len(ordered)
    stages = []
    seen = 0
    for fraction in stage_fractions:
        target = max(seen + 1, round(total * fraction)) if total else 0
        target = min(target, total)
        group = ordered[seen:target]
        if group:
            stages.append([h["hostname"] for h in group])
        seen = target
    if seen < total:
        stages.append([h["hostname"] for h in ordered[seen:]])
    return stages


def host_is_healthy(host, signals):
    """Health gate for one host after a change.

    `signals` has `cpu_util_pct` and `mem_used_pct`. A host fails the
    gate when CPU or memory is over the limit, or its recorded status
    is not healthy.
    """
    if host.get("status") != "healthy":
        return False
    if signals.get("cpu_util_pct", 0) > HEALTH_CPU_MAX_PCT:
        return False
    if signals.get("mem_used_pct", 0) > HEALTH_MEM_MAX_PCT:
        return False
    return True


def run_rollout(hosts, apply_change, rollback_change, health_signals,
                stage_fractions=DEFAULT_STAGES):
    """Roll a change out across the fleet in stages, with rollback.

    `apply_change(host)` and `rollback_change(host)` are callables.
    `health_signals` maps hostname -> signals dict for the health
    gate after each stage. A failed gate rolls back only the hosts
    in that stage and stops the rollout. Returns a report dict.
    """
    by_name = {h["hostname"]: h for h in hosts}
    report = {"stages_attempted": 0, "applied": [], "rolled_back": [],
              "failed_stage": None, "failed_hosts": [], "status": "complete"}
    for stage in stage_hosts(hosts, stage_fractions):
        report["stages_attempted"] += 1
        for name in stage:
            apply_change(by_name[name])
            report["applied"].append(name)
        failed = [name for name in stage
                  if not host_is_healthy(by_name[name],
                                         health_signals.get(name, {}))]
        if failed:
            for name in stage:
                rollback_change(by_name[name])
                report["applied"].remove(name)
                report["rolled_back"].append(name)
            report["failed_stage"] = report["stages_attempted"]
            report["failed_hosts"] = failed
            report["status"] = "rolled back"
            return report
    return report


def fleet_summary(hosts):
    """Fleet counts by role and status, plus the unhealthy hostnames."""
    by_role = {}
    by_status = {}
    unhealthy = []
    for host in hosts:
        by_role[host["role"]] = by_role.get(host["role"], 0) + 1
        by_status[host["status"]] = by_status.get(host["status"], 0) + 1
        if host["status"] != "healthy":
            unhealthy.append(host["hostname"])
    return {"total_hosts": len(hosts), "by_role": by_role,
            "by_status": by_status, "unhealthy_hosts": sorted(unhealthy)}
