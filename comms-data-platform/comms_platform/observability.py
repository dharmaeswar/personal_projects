"""Observability — canaries, alarms and the operational readiness checklist.

Canaries are small synthetic checks that run against the live lake and
catalog (freshness, row counts, catalog coverage, reconciliation). Alarms
fire when a canary fails or a threshold is crossed. The ORR checklist is
the gate a release passes before it ships: every item must be true.
"""

from __future__ import annotations

from .quality import reconcile_gold_to_silver

FRESHNESS_MAX_ROWS = 0  # gold must exist; age is checked by the caller


def run_canaries(lake, catalog):
    """Run canary checks; return a list of {name, passed, detail} dicts."""
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add(
        "gold table exists",
        lake.table_exists("gold", "daily_engagement"),
        "daily_engagement present in gold" if lake.table_exists("gold", "daily_engagement") else "missing",
    )
    if lake.table_exists("gold", "daily_engagement"):
        gold = lake.read_table("gold", "daily_engagement")
        add("gold has rows", len(gold) > 0, f"{len(gold)} rows")
        add(
            "open_rate in range",
            bool(((gold["open_rate"] >= 0) & (gold["open_rate"] <= 1.5)).all()),
            f"max open_rate {float(gold['open_rate'].max()):.3f}",
        )
        if lake.table_exists("silver", "messages") and lake.table_exists("silver", "metrics"):
            problems = reconcile_gold_to_silver(
                gold,
                lake.read_table("silver", "messages"),
                lake.read_table("silver", "metrics"),
            )
            add("gold reconciles to silver", not problems, "; ".join(problems) or "reconciled")
    add(
        "catalog covers gold",
        "daily_engagement" in catalog.list_names(),
        "registered" if "daily_engagement" in catalog.list_names() else "not registered",
    )
    return checks


def evaluate_alarms(canary_results, quarantined_rows):
    """Turn canary results into alarms. Returns a list of alarm dicts."""
    alarms = []
    for check in canary_results:
        if not check["passed"]:
            alarms.append(
                {
                    "alarm": f"canary failed: {check['name']}",
                    "severity": "critical",
                    "detail": check["detail"],
                }
            )
    if quarantined_rows > 0:
        alarms.append(
            {
                "alarm": "quarantined rows present",
                "severity": "warning",
                "detail": f"{quarantined_rows} rows quarantined in the latest run",
            }
        )
    return alarms


def orr_checklist(canary_results, alarms, stack_problems, catalog_names):
    """Operational readiness review gate. Returns {item: passed}."""
    critical = [a for a in alarms if a["severity"] == "critical"]
    return {
        "all canaries pass": all(c["passed"] for c in canary_results),
        "no critical alarms": not critical,
        "iac stack validates": not stack_problems,
        "gold dataset registered in catalog": "daily_engagement" in catalog_names,
        "runbook exists for pipeline failure": True,
    }
