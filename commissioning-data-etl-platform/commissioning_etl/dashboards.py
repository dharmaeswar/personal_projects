"""Dashboard datasets: progress, ticket aging, open defects, daily report.

These are the exact rows a dashboard binds to — progress by system and
area, ticket aging buckets by priority, and the open-defect list — plus a
plain-text daily report for the commissioning stand-up.
"""

from datetime import date

REPORT_DATE = "2026-11-27"
TICKET_AGE_SLA_DAYS = 30


def _age_days(created_at, report_date=REPORT_DATE):
    ref = date.fromisoformat(report_date)
    return (ref - date.fromisoformat(created_at)).days


def refresh_ticket_aging(conn, report_date=REPORT_DATE):
    """Rebuild the ticket-aging mart from bronze tickets."""
    conn.execute("DELETE FROM mart_ticket_aging")
    rows = conn.execute(
        "SELECT ticket_id, system_id, title, state, priority, created_at "
        "FROM bronze_tickets"
    ).fetchall()
    for ticket_id, system_id, title, state, priority, created_at in rows:
        age = _age_days(created_at, report_date)
        breach = 1 if age > TICKET_AGE_SLA_DAYS and state in ("Open", "In Progress") else 0
        conn.execute(
            "INSERT INTO mart_ticket_aging VALUES (?,?,?,?,?,?,?)",
            (ticket_id, system_id, title, state, priority, age, breach),
        )


def system_progress(conn):
    """One row per system, plus an area rollup row per area."""
    systems = conn.execute(
        "SELECT system_id, area, name, total_checkpoints, "
        "completed_checkpoints, pct_complete, open_defects "
        "FROM mart_system_progress ORDER BY area, system_id"
    ).fetchall()
    areas = conn.execute(
        "SELECT area, COUNT(*), SUM(total_checkpoints), "
        "SUM(completed_checkpoints), SUM(open_defects) "
        "FROM mart_system_progress GROUP BY area ORDER BY area"
    ).fetchall()
    return {"systems": systems, "areas": areas}


def ticket_aging(conn):
    """Ticket counts by age bucket (0-7, 8-30, 31+ days) and priority."""
    buckets = conn.execute(
        "SELECT CASE WHEN age_days <= 7 THEN '0-7 days' "
        "WHEN age_days <= 30 THEN '8-30 days' ELSE '31+ days' END AS bucket, "
        "priority, COUNT(*) FROM mart_ticket_aging "
        "WHERE state IN ('Open','In Progress') GROUP BY bucket, priority "
        "ORDER BY bucket, priority"
    ).fetchall()
    return buckets


def open_defects(conn):
    """Open / in-progress tickets, oldest first."""
    return conn.execute(
        "SELECT ticket_id, system_id, title, state, priority, age_days "
        "FROM mart_ticket_aging WHERE state IN ('Open','In Progress') "
        "ORDER BY age_days DESC"
    ).fetchall()


def daily_report(conn, report_date=REPORT_DATE):
    """Plain-text daily report for the commissioning stand-up."""
    prog = system_progress(conn)
    total = sum(r[2] for r in prog["areas"])
    done = sum(r[3] for r in prog["areas"])
    pct = round(100.0 * done / total, 1) if total else 0.0
    defects = open_defects(conn)
    breaches = [d for d in defects if d[5] > TICKET_AGE_SLA_DAYS]
    lines = [
        f"Commissioning daily report — {report_date}",
        f"Systems tracked: {len(prog['systems'])}; "
        f"checkpoints complete: {done}/{total} ({pct}%)",
    ]
    for area, n, t, c, o in prog["areas"]:
        area_pct = round(100.0 * c / t, 1) if t else 0.0
        lines.append(f"  {area}: {n} systems, {c}/{t} checkpoints ({area_pct}%), "
                     f"{o} open defects")
    lines.append(f"Open defects: {len(defects)}; past 30-day SLA: {len(breaches)}")
    for ticket_id, system_id, title, state, priority, age in defects[:5]:
        lines.append(f"  {ticket_id} [{priority}] {title} — {system_id}, "
                     f"{state}, {age} days old")
    return "\n".join(lines)
