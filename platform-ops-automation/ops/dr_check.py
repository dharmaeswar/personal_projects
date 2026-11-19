"""Disaster-recovery / failover readiness checks for the Platform Ops
Automation demo project.

Validates a readiness checklist from a plain config dict: runbook review
freshness, last failover test, backup verification freshness, and an
on-call roster. All dates are ISO strings (YYYY-MM-DD); `today` is a
`datetime.date`. Demo data only — no real systems are described.
"""

from datetime import date


def _parse(value):
    if isinstance(value, date):
        return value
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)


def check_readiness(config, today, max_failover_test_age_days=90,
                    max_backup_age_days=7, max_runbook_age_days=180):
    """Check each readiness item. Returns a list of check dicts with
    `name`, `status` ("pass"/"fail"), and a human-readable `detail`."""
    checks = []
    runbook_age = (today - _parse(config["runbook_last_reviewed"])).days
    checks.append(
        {
            "name": "runbook-reviewed",
            "status": "pass" if runbook_age <= max_runbook_age_days else "fail",
            "detail": f"runbook last reviewed {runbook_age} days ago "
            f"(limit {max_runbook_age_days})",
        }
    )
    failover_age = (today - _parse(config["last_failover_test"])).days
    checks.append(
        {
            "name": "failover-tested",
            "status": "pass" if failover_age <= max_failover_test_age_days else "fail",
            "detail": f"last failover test {failover_age} days ago "
            f"(limit {max_failover_test_age_days})",
        }
    )
    backup_age = (today - _parse(config["backup_last_verified"])).days
    checks.append(
        {
            "name": "backup-verified",
            "status": "pass" if backup_age <= max_backup_age_days else "fail",
            "detail": f"backup last verified {backup_age} days ago "
            f"(limit {max_backup_age_days})",
        }
    )
    roster = bool(config.get("oncall_roster_filled"))
    checks.append(
        {
            "name": "oncall-roster-filled",
            "status": "pass" if roster else "fail",
            "detail": "on-call roster filled" if roster else "on-call roster has gaps",
        }
    )
    return checks


def readiness_report(checks):
    """Summarize a list of checks: overall status plus pass/fail counts."""
    failed = [c for c in checks if c["status"] != "pass"]
    return {
        "overall": "fail" if failed else "pass",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_checks": [c["name"] for c in failed],
    }


def demo_config():
    """A demo config with one stale item (failover test 120 days old)."""
    return {
        "runbook_last_reviewed": "2026-10-01",
        "last_failover_test": "2026-07-22",
        "backup_last_verified": "2026-11-18",
        "oncall_roster_filled": True,
    }


def main():
    today = date(2026, 11, 19)
    checks = check_readiness(demo_config(), today)
    for check in checks:
        print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
    report = readiness_report(checks)
    print(
        f"overall={report['overall']} passed={report['passed']} "
        f"failed={report['failed']}"
    )


if __name__ == "__main__":
    main()
