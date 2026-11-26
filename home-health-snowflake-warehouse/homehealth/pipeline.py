"""DAG orchestration for the home-health pipeline.

Tasks run in dependency order (ingest -> validate -> load -> reconcile ->
publish). Each task gets one retry on failure. Run state lives in the
warehouse (``run_state`` table) so a failed run resumes instead of
re-loading, and a re-run of a completed run is a no-op for the load step.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from . import governance, ingest, quality, warehouse

TASKS = ("ingest", "validate", "load", "reconcile", "publish")
DEPENDENCIES = {
    "ingest": (),
    "validate": ("ingest",),
    "load": ("validate",),
    "reconcile": ("load",),
    "publish": ("reconcile",),
}


def task_order() -> list[str]:
    """Topological order of the DAG."""
    ordered: list[str] = []
    done: set[str] = set()
    while len(ordered) < len(TASKS):
        for task in TASKS:
            if task in done:
                continue
            if all(dep in done for dep in DEPENDENCIES[task]):
                ordered.append(task)
                done.add(task)
    return ordered


def get_task_status(conn: sqlite3.Connection, run_id: str, task: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM run_state WHERE run_id = ? AND task = ?",
        (run_id, task),
    ).fetchone()
    return row[0] if row else None


def set_task_status(
    conn: sqlite3.Connection, run_id: str, task: str, status: str
) -> None:
    conn.execute(
        "INSERT INTO run_state (run_id, task, status) VALUES (?, ?, ?) "
        "ON CONFLICT(run_id, task) DO UPDATE SET status = excluded.status",
        (run_id, task, status),
    )
    conn.commit()


def run(
    conn: sqlite3.Connection,
    visits_path: str,
    referrals_path: str,
    run_id: str,
    today: date | None = None,
    incremental: bool = True,
) -> dict:
    """Run the full pipeline. Returns the run report."""
    today = today or date.today()
    report: dict = {"run_id": run_id, "tasks": {}}
    context: dict = {}

    def do_ingest() -> None:
        visits = ingest.read_visit_csv(visits_path)
        pages = ingest.load_referral_fixture(referrals_path)
        client = ingest.ReferralApiClient(pages, fail_first_fetch=True)
        referrals = ingest.fetch_referrals(client)
        context["visits"] = visits.records
        context["visit_errors"] = visits.errors
        context["referrals"] = referrals.records
        context["api_retries"] = referrals.api_retries
        context["referral_errors"] = referrals.errors

    def do_validate() -> None:
        valid, quarantined = quality.validate_visits(context["visits"], today)
        context["valid"] = valid
        context["quarantined"] = quarantined

    def do_load() -> None:
        result = warehouse.load_visits(
            conn,
            context["valid"],
            context["quarantined"],
            run_id,
            source_rows=len(context["visits"]),
            incremental=incremental,
        )
        context["load"] = result
        governance.audit(
            conn,
            run_id,
            "load",
            f"loaded {result['loaded']}, "
            f"quarantined {result['quarantined']}",
            today.isoformat(),
        )

    def do_reconcile() -> None:
        load = context["load"]
        if not load["reconciled"]:
            raise ValueError(
                "reconciliation failed: source rows do not equal "
                "loaded + skipped + quarantined"
            )
        context["reconciled"] = True

    def do_publish() -> None:
        rows = conn.execute(
            "SELECT visit_date, visits, total_minutes, "
            "avg_assessment_score FROM v_visit_summary"
        ).fetchall()
        context["summary"] = [dict(row) for row in rows]

    steps = {
        "ingest": do_ingest,
        "validate": do_validate,
        "load": do_load,
        "reconcile": do_reconcile,
        "publish": do_publish,
    }
    for task in task_order():
        # A re-run of the same run_id re-executes every step; the load step
        # is idempotent (watermark + INSERT OR IGNORE on visit_id), so a
        # resumed run loads only what is new instead of duplicating rows.
        attempts = 0
        while True:
            try:
                steps[task]()
                set_task_status(conn, run_id, task, "done")
                report["tasks"][task] = "done"
                break
            except Exception as exc:  # noqa: BLE001 - retry once, then fail
                attempts += 1
                if attempts > 1:
                    set_task_status(conn, run_id, task, "failed")
                    raise
                report["tasks"][task] = f"retrying after {exc}"
    report["source_rows"] = len(context["visits"])
    report["referrals"] = len(context["referrals"])
    report["api_retries"] = context["api_retries"]
    report["loaded"] = context["load"]["loaded"]
    report["quarantined"] = context["load"]["quarantined"]
    report["fact_rows"] = context["load"]["fact_rows"]
    report["reconciled"] = context["load"]["reconciled"]
    report["summary"] = context["summary"]
    return report
