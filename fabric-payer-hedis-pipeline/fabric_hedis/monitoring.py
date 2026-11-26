"""Production support: pipeline health monitoring and alerting.

The on-call job for this role is keeping the monthly payer processing
healthy: files must arrive on time, row counts must not swing wildly
month to month, quarantine must stay low, and any job failure must page
someone with the failing step named. These checks run at the end of
every monthly run and write their findings to ``run_log``; an alert is
a row in the returned list, not a silent log line.
"""

QUARANTINE_RATE_LIMIT = 0.05   # more than 5% quarantined -> alert
ROW_SWING_LIMIT = 0.20         # >20% change vs last month -> anomaly


def record_run(conn, run_id, step, status, detail=""):
    conn.execute(
        "INSERT INTO run_log (run_id, step, status, detail)"
        " VALUES (?, ?, ?, ?)", (run_id, step, status, detail))
    conn.commit()


def health_checks(conn, month, stats):
    """Run the health checks for a finished monthly load.

    Returns a list of alert dicts {severity, check, detail}. An empty
    list means the run is healthy.
    """
    alerts = []
    bronze = stats["bronze_claims"]
    quarantined = stats["quarantined"]
    if bronze:
        rate = quarantined / bronze
        if rate > QUARANTINE_RATE_LIMIT:
            alerts.append({
                "severity": "warning",
                "check": "quarantine_rate",
                "detail": "quarantine rate %.1f%% (%d of %d claims) is over"
                          " the %.0f%% limit"
                          % (rate * 100, quarantined, bronze,
                             QUARANTINE_RATE_LIMIT * 100)})
    prev = conn.execute(
        "SELECT bronze_claims FROM run_stats WHERE measurement_month < ?"
        " ORDER BY measurement_month DESC LIMIT 1", (month,)).fetchone()
    if prev is not None and prev[0]:
        swing = abs(bronze - prev[0]) / prev[0]
        if swing > ROW_SWING_LIMIT:
            alerts.append({
                "severity": "anomaly",
                "check": "row_count_swing",
                "detail": "bronze claims %d vs %d last month (%.1f%% swing,"
                          " limit %.0f%%)"
                          % (bronze, prev[0], swing * 100,
                             ROW_SWING_LIMIT * 100)})
    failures = conn.execute(
        "SELECT step, detail FROM run_log WHERE status = 'failed'"
        " AND run_id LIKE ? ORDER BY logged_at",
        ("%" + month + "%",)).fetchall()
    for step, detail in failures:
        alerts.append({"severity": "critical", "check": "job_failure",
                       "detail": "step %s failed: %s" % (step, detail)})
    return alerts


def summarize_alerts(alerts):
    if not alerts:
        return "HEALTHY: no alerts"
    lines = ["%s [%s] %s" % (a["severity"].upper(), a["check"], a["detail"])
             for a in alerts]
    return "%d alert(s):\n%s" % (len(alerts), "\n".join(lines))
