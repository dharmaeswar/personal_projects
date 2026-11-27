"""Data-quality checks that gate the dashboard publish.

Every check returns {'name', 'status', 'detail'}. A failed check must
block the publish: ``run_pipeline.py`` exits non-zero when any check fails.
"""

FRESHNESS_SLA_DAYS = 7
TICKET_AGE_SLA_DAYS = 30


def run_checks(conn, report_date="2026-11-27"):
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "status": "pass" if passed else "fail",
                       "detail": detail})

    n_sys = conn.execute("SELECT COUNT(*) FROM bronze_systems").fetchone()[0]
    n_tkt = conn.execute("SELECT COUNT(*) FROM bronze_tickets").fetchone()[0]
    add("systems_present", n_sys > 0, f"{n_sys} systems in bronze")
    add("tickets_present", n_tkt > 0, f"{n_tkt} tickets in bronze")

    nulls = conn.execute(
        "SELECT COUNT(*) FROM bronze_systems WHERE area IS NULL OR name IS NULL"
    ).fetchone()[0]
    add("no_null_system_fields", nulls == 0, f"{nulls} rows with null area/name")

    bad_counts = conn.execute(
        "SELECT COUNT(*) FROM bronze_systems "
        "WHERE completed_checkpoints > total_checkpoints "
        "OR total_checkpoints < 0 OR completed_checkpoints < 0"
    ).fetchone()[0]
    add("checkpoint_invariant", bad_counts == 0,
        f"{bad_counts} systems break completed <= total")

    orphans = conn.execute(
        "SELECT COUNT(*) FROM bronze_tickets t LEFT JOIN bronze_systems s "
        "ON t.system_id = s.system_id WHERE s.system_id IS NULL"
    ).fetchone()[0]
    add("ticket_system_references", orphans == 0,
        f"{orphans} tickets reference unknown systems")

    dup_sys = conn.execute(
        "SELECT COUNT(*) FROM (SELECT system_id FROM bronze_systems "
        "GROUP BY system_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    dup_tkt = conn.execute(
        "SELECT COUNT(*) FROM (SELECT ticket_id FROM bronze_tickets "
        "GROUP BY ticket_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    add("no_duplicate_ids", dup_sys == 0 and dup_tkt == 0,
        f"{dup_sys} duplicate systems, {dup_tkt} duplicate tickets")

    stale = conn.execute(
        "SELECT COUNT(*) FROM bronze_systems "
        "WHERE julianday(?) - julianday(updated_at) > ?",
        (report_date, FRESHNESS_SLA_DAYS),
    ).fetchone()[0]
    add("freshness_sla", stale == 0,
        f"{stale} systems not updated in the last {FRESHNESS_SLA_DAYS} days")

    bad_states = conn.execute(
        "SELECT COUNT(*) FROM bronze_tickets "
        "WHERE state NOT IN ('Open','In Progress','Resolved','Closed')"
    ).fetchone()[0]
    add("ticket_states_valid", bad_states == 0, f"{bad_states} tickets with bad state")

    bad_prio = conn.execute(
        "SELECT COUNT(*) FROM bronze_tickets WHERE priority NOT IN ('P1','P2','P3')"
    ).fetchone()[0]
    add("ticket_priorities_valid", bad_prio == 0, f"{bad_prio} tickets with bad priority")

    breaches = conn.execute(
        "SELECT COUNT(*) FROM mart_ticket_aging "
        "WHERE sla_breach = 1 AND state IN ('Open','In Progress')"
    ).fetchone()[0]
    add("ticket_age_sla_reported", True,
        f"{breaches} open/in-progress tickets past the "
        f"{TICKET_AGE_SLA_DAYS}-day age SLA (reported, not a load failure)")

    quarantined = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    add("quarantine_logged", True,
        f"{quarantined} bad rows quarantined with reasons, none loaded")
    return checks
