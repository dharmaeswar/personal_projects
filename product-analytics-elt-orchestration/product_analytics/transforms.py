"""Window-function transforms: sessions, retention, funnels.

All three transforms are plain SQL window functions over the partitioned
tables, so the same queries run unchanged against any warehouse that
speaks SQL. Sessionization uses LAG() over each user's event stream with
a 30-minute inactivity gap. Retention cohorts anchor on each user's
first active day. The funnel uses MIN() per user per day to find the
first view, save and click in order.
"""
from __future__ import annotations

import sqlite3

SESSION_GAP_SECONDS = 30 * 60


def build_sessions(conn: sqlite3.Connection, gap_seconds: int = SESSION_GAP_SECONDS) -> dict:
    """Group events into sessions: a new session starts after a long gap."""
    conn.execute("DELETE FROM sessions")
    conn.execute(
        """
        INSERT INTO sessions (session_id, user_id, session_date, started_at, ended_at,
                              event_count, duration_sec)
        WITH ordered AS (
            SELECT event_id, user_id, event_ts,
                   LAG(event_ts) OVER (PARTITION BY user_id ORDER BY event_ts) AS prev_ts
            FROM staged_events
        ),
        flagged AS (
            SELECT event_id, user_id, event_ts,
                   CASE WHEN prev_ts IS NULL
                             OR (strftime('%s', event_ts) - strftime('%s', prev_ts)) > ?
                        THEN 1 ELSE 0 END AS is_new
            FROM ordered
        ),
        grouped AS (
            SELECT event_id, user_id, event_ts,
                   SUM(is_new) OVER (PARTITION BY user_id ORDER BY event_ts
                                      ROWS UNBOUNDED PRECEDING) AS session_no
            FROM flagged
        )
        SELECT user_id || '_' || session_no,
               user_id, substr(MIN(event_ts), 1, 10), MIN(event_ts), MAX(event_ts),
               COUNT(*),
               CAST(strftime('%s', MAX(event_ts)) - strftime('%s', MIN(event_ts)) AS INTEGER)
        FROM grouped
        GROUP BY user_id, session_no
        """,
        (gap_seconds,),
    )
    conn.commit()
    return {"sessions": conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]}


def retention(conn: sqlite3.Connection, cohort_days: int = 7) -> list[dict]:
    """Day-N retention per first-active-day cohort, for N = 1..cohort_days."""
    rows = conn.execute(
        """
        WITH first_seen AS (
            SELECT user_id, MIN(event_date) AS cohort_date FROM staged_events GROUP BY user_id
        ),
        activity AS (
            SELECT DISTINCT f.cohort_date, s.user_id,
                   CAST(julianday(s.event_date) - julianday(f.cohort_date) AS INTEGER) AS day_n
            FROM first_seen f JOIN staged_events s ON s.user_id = f.user_id
        )
        SELECT cohort_date, day_n, COUNT(DISTINCT user_id) AS users
        FROM activity
        WHERE day_n BETWEEN 1 AND ?
        GROUP BY cohort_date, day_n
        ORDER BY cohort_date, day_n
        """,
        (cohort_days,),
    ).fetchall()
    return [dict(r) for r in rows]


def funnel(conn: sqlite3.Connection, date: str) -> dict:
    """View -> save -> click funnel for one day, using first event per user."""
    row = conn.execute(
        """
        WITH firsts AS (
            SELECT user_id,
                   MIN(CASE WHEN event_type = 'page_view' THEN event_ts END) AS viewed_at,
                   MIN(CASE WHEN event_type = 'pin_save' THEN event_ts END) AS saved_at,
                   MIN(CASE WHEN event_type = 'pin_click' THEN event_ts END) AS clicked_at
            FROM staged_events
            WHERE event_date = ?
            GROUP BY user_id
        )
        SELECT COUNT(viewed_at) AS viewers,
               SUM(CASE WHEN saved_at IS NOT NULL AND saved_at >= viewed_at THEN 1 ELSE 0 END) AS savers,
               SUM(CASE WHEN clicked_at IS NOT NULL AND saved_at IS NOT NULL
                             AND clicked_at >= saved_at THEN 1 ELSE 0 END) AS clickers
        FROM firsts
        """,
        (date,),
    ).fetchone()
    return dict(row)


def dau(conn: sqlite3.Connection, date: str) -> int:
    """Daily active users for one date."""
    return conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM staged_events WHERE event_date = ?",
        (date,),
    ).fetchone()[0]
