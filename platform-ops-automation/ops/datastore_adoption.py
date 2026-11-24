"""Data-store adoption readiness for the Platform Ops Automation demo
project.

Models the "adopt and operationalize new data stores" work on a cloud
infrastructure roadmap (the shape of a Vitess / ClickHouse / Redis
evaluation): a candidate store is scored against the checks an
infrastructure team runs before it carries production traffic —
replication, durability and backups, latency SLO, observability
hooks, failover-test freshness, and the security / data-residency
gates enterprise deployments require. Plain dicts in, checks out.
Demo data only — no real datastore is contacted, and no production
adoption experience is claimed.
"""

DEFAULT_MIN_REPLICAS = 3
DEFAULT_MAX_P99_READ_MS = 10
DEFAULT_MAX_P99_WRITE_MS = 25
DEFAULT_MAX_FAILOVER_TEST_AGE_DAYS = 90
DEFAULT_MAX_BACKUP_RESTORE_TEST_AGE_DAYS = 30


def check_adoption(candidate,
                   min_replicas=DEFAULT_MIN_REPLICAS,
                   max_p99_read_ms=DEFAULT_MAX_P99_READ_MS,
                   max_p99_write_ms=DEFAULT_MAX_P99_WRITE_MS,
                   max_failover_test_age_days=DEFAULT_MAX_FAILOVER_TEST_AGE_DAYS,
                   max_backup_restore_test_age_days=DEFAULT_MAX_BACKUP_RESTORE_TEST_AGE_DAYS):
    """Check one candidate store. `candidate` is a dict with `name`,
    `replicas`, `p99_read_ms`, `p99_write_ms`, `durable_writes` (bool),
    `backups_enabled` (bool), `backup_restore_test_age_days`,
    `failover_test_age_days`, `observability` (bool — metrics, logs and
    traces wired up), `encryption_at_rest` (bool) and
    `data_residency_ok` (bool). Returns a list of check dicts with
    `name`, `status` ("pass"/"fail") and a human-readable `detail`."""
    checks = []
    checks.append(
        {
            "name": "replication",
            "status": "pass" if candidate["replicas"] >= min_replicas else "fail",
            "detail": f"{candidate['replicas']} replicas "
            f"(minimum {min_replicas})",
        }
    )
    checks.append(
        {
            "name": "durable-writes",
            "status": "pass" if candidate["durable_writes"] else "fail",
            "detail": "durable writes enabled"
            if candidate["durable_writes"]
            else "writes are not durable (no WAL / fsync)",
        }
    )
    checks.append(
        {
            "name": "backups",
            "status": "pass" if candidate["backups_enabled"] else "fail",
            "detail": "scheduled backups enabled"
            if candidate["backups_enabled"]
            else "no scheduled backups",
        }
    )
    checks.append(
        {
            "name": "backup-restore-test",
            "status": "pass"
            if candidate["backup_restore_test_age_days"]
            <= max_backup_restore_test_age_days
            else "fail",
            "detail": f"last restore test "
            f"{candidate['backup_restore_test_age_days']} days ago "
            f"(limit {max_backup_restore_test_age_days})",
        }
    )
    checks.append(
        {
            "name": "p99-read",
            "status": "pass"
            if candidate["p99_read_ms"] <= max_p99_read_ms
            else "fail",
            "detail": f"p99 read {candidate['p99_read_ms']} ms "
            f"(limit {max_p99_read_ms})",
        }
    )
    checks.append(
        {
            "name": "p99-write",
            "status": "pass"
            if candidate["p99_write_ms"] <= max_p99_write_ms
            else "fail",
            "detail": f"p99 write {candidate['p99_write_ms']} ms "
            f"(limit {max_p99_write_ms})",
        }
    )
    checks.append(
        {
            "name": "observability",
            "status": "pass" if candidate["observability"] else "fail",
            "detail": "metrics, logs and traces wired up"
            if candidate["observability"]
            else "no metrics / logs / traces wired up",
        }
    )
    checks.append(
        {
            "name": "failover-test",
            "status": "pass"
            if candidate["failover_test_age_days"]
            <= max_failover_test_age_days
            else "fail",
            "detail": f"last failover test "
            f"{candidate['failover_test_age_days']} days ago "
            f"(limit {max_failover_test_age_days})",
        }
    )
    checks.append(
        {
            "name": "encryption-at-rest",
            "status": "pass" if candidate["encryption_at_rest"] else "fail",
            "detail": "encryption at rest enabled"
            if candidate["encryption_at_rest"]
            else "no encryption at rest",
        }
    )
    checks.append(
        {
            "name": "data-residency",
            "status": "pass" if candidate["data_residency_ok"] else "fail",
            "detail": "data residency requirements met"
            if candidate["data_residency_ok"]
            else "data residency requirements not met",
        }
    )
    return checks


def adoption_summary(candidate):
    """Aggregate one candidate into a summary dict with a verdict:
    "adopt" (all checks pass), "pilot" (only non-blocking checks fail)
    or "not ready" (a blocking check fails). Blocking checks are
    replication, durable writes, backups and encryption at rest."""
    checks = check_adoption(candidate)
    failed = [c for c in checks if c["status"] == "fail"]
    blocking = {"replication", "durable-writes", "backups",
                "encryption-at-rest"}
    blocked = [c for c in failed if c["name"] in blocking]
    if not failed:
        verdict = "adopt"
    elif blocked:
        verdict = "not ready"
    else:
        verdict = "pilot"
    return {
        "name": candidate["name"],
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "failed_checks": [c["name"] for c in failed],
        "verdict": verdict,
    }


def demo_candidates():
    """Three synthetic candidates in the shape of a Redis-style cache,
    a ClickHouse-style analytics store and a Vitess-style sharded
    store. The analytics store has a stale failover test, so its
    verdict is "pilot"; the sharded store has no durable writes, so
    it is "not ready"."""
    base = {
        "replicas": 3, "p99_read_ms": 4.0, "p99_write_ms": 9.0,
        "durable_writes": True, "backups_enabled": True,
        "backup_restore_test_age_days": 12,
        "failover_test_age_days": 40, "observability": True,
        "encryption_at_rest": True, "data_residency_ok": True,
    }
    cache = dict(base, name="cache-store")
    analytics = dict(base, name="analytics-store", p99_read_ms=8.0,
                     failover_test_age_days=140)
    sharded = dict(base, name="sharded-store", replicas=2,
                   durable_writes=False, p99_write_ms=31.0)
    return [cache, analytics, sharded]


def adoption_report(candidates):
    """One-line-per-candidate text report."""
    lines = []
    for candidate in candidates:
        summary = adoption_summary(candidate)
        lines.append(
            f"{summary['name']}: {summary['verdict']} "
            f"({summary['checks_passed']}/{summary['checks_total']} "
            f"checks pass)"
        )
        for check in check_adoption(candidate):
            mark = "PASS" if check["status"] == "pass" else "FAIL"
            lines.append(f"  [{mark}] {check['name']}: {check['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(adoption_report(demo_candidates()))
