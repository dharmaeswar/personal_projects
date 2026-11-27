"""Data validation, quality assurance and reconciliation.

Every check returns an exception dict; bad rows are queued for review
and never silently dropped or included in the KPIs. Valid rows are the
transactions that pass every check.
"""

CHECKS = ["negative_amount", "missing_amount", "duplicate_txn_id", "orphan_account"]


def validate_transactions(conn):
    """Return (valid_rows, exceptions) for the transactions table."""
    rows = conn.execute("SELECT * FROM transactions ORDER BY row_id").fetchall()
    account_ids = {r["account_id"] for r in conn.execute("SELECT account_id FROM accounts")}
    client_ids = {r["client_id"] for r in conn.execute("SELECT client_id FROM clients")}
    account_client = {r["account_id"]: r["client_id"]
                      for r in conn.execute("SELECT account_id, client_id FROM accounts")}
    seen_txn = set()
    valid, exceptions = [], []
    for row in rows:
        d = dict(row)
        problems = []
        if d["amount"] is None:
            problems.append("missing_amount")
        elif d["amount"] < 0:
            problems.append("negative_amount")
        if d["txn_id"] in seen_txn:
            problems.append("duplicate_txn_id")
        seen_txn.add(d["txn_id"])
        if d["account_id"] not in account_ids:
            problems.append("orphan_account")
        elif account_client[d["account_id"]] not in client_ids:
            problems.append("orphan_account")
        if problems:
            for p in problems:
                exceptions.append({"txn_id": d["txn_id"], "check": p,
                                   "detail": f"amount={d['amount']} account={d['account_id']}"})
        else:
            valid.append(d)
    return valid, exceptions


def validate_accounts(conn):
    """Return exceptions for accounts whose client does not exist."""
    exceptions = []
    for row in conn.execute(
            "SELECT a.account_id, a.client_id FROM accounts a"
            " LEFT JOIN clients c ON c.client_id = a.client_id"
            " WHERE c.client_id IS NULL"):
        exceptions.append({"account_id": row["account_id"], "check": "orphan_account",
                           "detail": f"client={row['client_id']} has no client record"})
    return exceptions


def reconcile_python_vs_sql(conn, valid):
    """Compare Python aggregates with SQL GROUP BY aggregates.

    Returns a list of mismatches (empty when the two agree within 0.01).
    """
    py_totals = {}
    for d in valid:
        key = (d["month"], d["channel"])
        py_totals[key] = py_totals.get(key, 0.0) + d["amount"]
    sql_rows = conn.execute(
        "SELECT month, channel, SUM(amount) AS total FROM transactions t"
        " WHERE amount IS NOT NULL AND amount >= 0"
        " AND t.row_id = (SELECT MIN(row_id) FROM transactions t2"
        "                WHERE t2.txn_id = t.txn_id)"
        " AND t.account_id IN (SELECT a.account_id FROM accounts a"
        "                      JOIN clients c ON c.client_id = a.client_id)"
        " GROUP BY month, channel").fetchall()
    sql_totals = {(r["month"], r["channel"]): r["total"] for r in sql_rows}
    mismatches = []
    for key, py_total in py_totals.items():
        sql_total = sql_totals.get(key)
        if sql_total is None or abs(py_total - sql_total) > 0.01:
            mismatches.append({"month": key[0], "channel": key[1],
                               "python_total": round(py_total, 2),
                               "sql_total": None if sql_total is None else round(sql_total, 2)})
    for key in sql_totals:
        if key not in py_totals:
            mismatches.append({"month": key[0], "channel": key[1],
                               "python_total": 0.0, "sql_total": round(sql_totals[key], 2)})
    return mismatches
