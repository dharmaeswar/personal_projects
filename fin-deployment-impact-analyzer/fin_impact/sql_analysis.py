"""SQL analysis over the conversation store (sqlite3, standard library).

Every metric a forward-deployed data scientist reports to a customer —
resolution rate, automation rate, deflection, handle time, CSAT,
escalation rate — is computed in SQL, so the numbers in the report
match the numbers in the warehouse query exactly.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conv_id TEXT PRIMARY KEY,
    customer TEXT,
    channel TEXT,
    period TEXT,
    resolved_by_fin INTEGER,
    handle_minutes REAL,
    csat INTEGER,
    escalated INTEGER
);
"""


def load(conn, conversations):
    """Load conversation rows into the store (idempotent reload)."""
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM conversations")
    conn.executemany(
        "INSERT INTO conversations VALUES (?,?,?,?,?,?,?,?)",
        [c.as_row() for c in conversations])
    conn.commit()


def _one(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def metrics(conn, customer=None):
    """Deployment metrics, overall or for one customer.

    Returns resolution (automation) rate, mean handle time, mean CSAT,
    escalation rate, and conversation counts — split by period.
    """
    where = "WHERE customer = ?" if customer else ""
    params = (customer,) if customer else ()
    out = {}
    for period in ("before", "after"):
        w = f"{where} AND period = ?" if where else "WHERE period = ?"
        p = params + (period,) if where else (period,)
        total = _one(conn, f"SELECT COUNT(*) FROM conversations {w}", p)
        resolved = _one(
            conn,
            f"SELECT COALESCE(SUM(resolved_by_fin),0) FROM conversations {w}",
            p)
        handle = _one(
            conn,
            f"SELECT COALESCE(AVG(handle_minutes),0) FROM conversations {w}",
            p)
        csat = _one(
            conn,
            f"SELECT AVG(csat) FROM conversations {w} AND csat IS NOT NULL",
            p)
        esc = _one(
            conn,
            f"SELECT COALESCE(SUM(escalated),0) FROM conversations {w}", p)
        out[period] = {
            "conversations": total,
            "resolution_rate": round(resolved / total, 4) if total else 0.0,
            "mean_handle_minutes": round(handle, 2),
            "mean_csat": round(csat, 2) if csat is not None else None,
            "escalation_rate": round(esc / total, 4) if total else 0.0,
        }
    return out


def by_channel(conn):
    """After-deployment resolution rate and handle time per channel."""
    rows = conn.execute(
        """SELECT channel, COUNT(*), COALESCE(SUM(resolved_by_fin),0),
                  COALESCE(AVG(handle_minutes),0)
           FROM conversations WHERE period = 'after'
           GROUP BY channel ORDER BY channel""").fetchall()
    return [{"channel": r[0], "conversations": r[1],
             "resolution_rate": round(r[2] / r[1], 4) if r[1] else 0.0,
             "mean_handle_minutes": round(r[3], 2)} for r in rows]


def connect(path=":memory:"):
    """Open the store. Production-aware default: a file path is expected
    by callers; in-memory is for tests and the demo run."""
    return sqlite3.connect(path)
