"""Medallion pipeline: bronze -> silver -> gold, backed by SQLite.

Bronze is the raw ingest (nothing cleaned, so bad source rows are visible).
Silver keeps only rows that pass every quality check; every rejected row
goes to a quarantine table with the reason it failed, so nothing is dropped
silently. Gold is built from silver with a real SQL GROUP BY query.
Late-arriving rows are valid data: they land in silver flagged
``late_arriving = 1`` and are counted, not quarantined.

Lineage: every silver row records the bronze ``event_id`` it came from,
and every gold group records the silver ``event_id`` values that fed it.
Each table write appends a versioned entry to a JSON transaction log
(``pipeline_log.json``), so any table can be traced back to the write
that produced it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .checks import (
    check_clicks_within_impressions,
    check_completeness,
    check_ranges,
    check_referential_integrity,
    check_spend_arithmetic,
    check_uniqueness,
)
from .data import MAX_EVENT_TS, MIN_EVENT_TS, WATERMARK_TS
from .schema import EVENTS_SCHEMA, SILVER_SCHEMA, enforce_schema

DB_TABLES = ("campaigns", "ads", "events_bronze", "events_silver", "quarantine", "gold_daily_spend")


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id TEXT PRIMARY KEY, advertiser TEXT NOT NULL,
            channel TEXT NOT NULL, start_date TEXT NOT NULL,
            end_date TEXT NOT NULL, daily_budget_usd REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS ads (
            ad_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL,
            format TEXT NOT NULL, placement TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events_bronze (
            event_id TEXT, ad_id TEXT, campaign_id TEXT, event_ts TEXT,
            impressions INTEGER, clicks INTEGER,
            cpc_usd REAL, spend_usd REAL);
        CREATE TABLE IF NOT EXISTS events_silver (
            event_id TEXT PRIMARY KEY, ad_id TEXT NOT NULL,
            campaign_id TEXT NOT NULL, event_ts TEXT NOT NULL,
            impressions INTEGER NOT NULL, clicks INTEGER NOT NULL,
            cpc_usd REAL NOT NULL, spend_usd REAL NOT NULL,
            late_arriving INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS quarantine (
            event_id TEXT, ad_id TEXT, campaign_id TEXT, event_ts TEXT,
            impressions INTEGER, clicks INTEGER,
            cpc_usd REAL, spend_usd REAL, quarantine_reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gold_daily_spend (
            event_date TEXT NOT NULL, campaign_id TEXT NOT NULL,
            channel TEXT NOT NULL, impressions INTEGER NOT NULL,
            clicks INTEGER NOT NULL, spend_usd REAL NOT NULL,
            PRIMARY KEY (event_date, campaign_id));
        """
    )
    conn.commit()


def load_bronze(
    conn: sqlite3.Connection,
    campaigns: list[dict],
    ads: list[dict],
    events: list[dict],
) -> None:
    """Load raw dimension and event data into the bronze tables."""
    _create_tables(conn)
    conn.execute("DELETE FROM campaigns")
    conn.execute("DELETE FROM ads")
    conn.execute("DELETE FROM events_bronze")
    conn.executemany(
        "INSERT INTO campaigns VALUES (?,?,?,?,?,?)",
        [(c["campaign_id"], c["advertiser"], c["channel"], c["start_date"], c["end_date"], c["daily_budget_usd"]) for c in campaigns],
    )
    conn.executemany(
        "INSERT INTO ads VALUES (?,?,?,?)",
        [(a["ad_id"], a["campaign_id"], a["format"], a["placement"]) for a in ads],
    )
    conn.executemany(
        "INSERT INTO events_bronze VALUES (?,?,?,?,?,?,?,?)",
        [(e["event_id"], e["ad_id"], e["campaign_id"], e["event_ts"], e["impressions"], e["clicks"], e["cpc_usd"], e["spend_usd"]) for e in events],
    )
    conn.commit()


def read_table(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def _flag_bad_rows(
    events: list[dict], ads: list[dict], campaigns: list[dict]
) -> tuple[set[int], dict[int, list[str]]]:
    """Return (bad row positions, reasons per row) for every quality check."""
    reasons: dict[int, list[str]] = {}
    checks = [
        ("null key", check_completeness(events, ["campaign_id", "ad_id", "event_ts"])),
        ("duplicate event_id", check_uniqueness(events, "event_id")),
        ("impressions out of range", check_ranges(events, "impressions", low=0)),
        ("clicks out of range", check_ranges(events, "clicks", low=0)),
        ("spend out of range", check_ranges(events, "spend_usd", low=0)),
        ("clicks exceed impressions", check_clicks_within_impressions(events)),
        (
            "event_ts out of range",
            check_ranges(events, "event_ts", low=MIN_EVENT_TS, high=MAX_EVENT_TS),
        ),
        (
            "unknown ad_id",
            check_referential_integrity(events, "ad_id", ads, "ad_id"),
        ),
        (
            "unknown campaign_id",
            check_referential_integrity(events, "campaign_id", campaigns, "campaign_id"),
        ),
        ("wrong spend", check_spend_arithmetic(events)),
    ]
    for label, result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(label)
    return set(reasons), reasons


def build_silver(
    conn: sqlite3.Connection,
    events: list[dict],
    ads: list[dict],
    campaigns: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Clean bronze events into silver + quarantine.

    Returns (silver, quarantine, lineage). Silver rows carry
    ``late_arriving`` (1 when the event arrived after the watermark).
    Lineage rows map each silver ``event_id`` to its bronze ``event_id``.
    """
    bad, reasons = _flag_bad_rows(events, ads, campaigns)
    silver: list[dict] = []
    quarantine: list[dict] = []
    lineage: list[dict] = []
    for i, event in enumerate(events):
        if i in bad:
            row = dict(event)
            row["quarantine_reason"] = "; ".join(reasons[i])
            quarantine.append(row)
            continue
        row = dict(event)
        row["late_arriving"] = 1 if event["event_ts"] < WATERMARK_TS else 0
        silver.append(row)
        lineage.append(
            {
                "silver_event_id": event["event_id"],
                "bronze_event_id": event["event_id"],
                "source_table": "events_bronze",
            }
        )
    problems = enforce_schema(silver, SILVER_SCHEMA, "events_silver")
    assert not problems, problems

    conn.execute("DELETE FROM events_silver")
    conn.execute("DELETE FROM quarantine")
    conn.executemany(
        "INSERT INTO events_silver VALUES (?,?,?,?,?,?,?,?,?)",
        [(r["event_id"], r["ad_id"], r["campaign_id"], r["event_ts"], r["impressions"], r["clicks"], r["cpc_usd"], r["spend_usd"], r["late_arriving"]) for r in silver],
    )
    conn.executemany(
        "INSERT INTO quarantine VALUES (?,?,?,?,?,?,?,?,?)",
        [(r["event_id"], r["ad_id"], r["campaign_id"], r["event_ts"], r["impressions"], r["clicks"], r["cpc_usd"], r["spend_usd"], r["quarantine_reason"]) for r in quarantine],
    )
    conn.commit()
    return silver, quarantine, lineage


def build_gold(
    conn: sqlite3.Connection, silver: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Aggregate silver into daily spend by campaign with a SQL GROUP BY.

    Returns (gold, gold_lineage). Gold lineage maps each
    (event_date, campaign_id) group to the silver event_ids that fed it.
    """
    rows = conn.execute(
        """
        SELECT substr(s.event_ts, 1, 10) AS event_date,
               s.campaign_id AS campaign_id,
               c.channel AS channel,
               SUM(s.impressions) AS impressions,
               SUM(s.clicks) AS clicks,
               ROUND(SUM(s.spend_usd), 2) AS spend_usd
        FROM events_silver s
        JOIN campaigns c ON c.campaign_id = s.campaign_id
        GROUP BY event_date, s.campaign_id, c.channel
        ORDER BY event_date, s.campaign_id
        """
    ).fetchall()
    gold = [dict(r) for r in rows]

    grouped: dict[tuple[str, str], list[str]] = {}
    for r in silver:
        grouped.setdefault((r["event_ts"][:10], r["campaign_id"]), []).append(r["event_id"])
    channel_of = {
        dict(row)["campaign_id"]: dict(row)["channel"]
        for row in conn.execute("SELECT campaign_id, channel FROM campaigns")
    }
    gold_lineage = [
        {
            "event_date": date,
            "campaign_id": campaign_id,
            "channel": channel_of[campaign_id],
            "source_event_ids": sorted(ids),
            "source_row_count": len(ids),
        }
        for (date, campaign_id), ids in sorted(grouped.items())
    ]

    conn.execute("DELETE FROM gold_daily_spend")
    conn.executemany(
        "INSERT INTO gold_daily_spend VALUES (?,?,?,?,?,?)",
        [(g["event_date"], g["campaign_id"], g["channel"], g["impressions"], g["clicks"], g["spend_usd"]) for g in gold],
    )
    conn.commit()
    return gold, gold_lineage


def read_log(log_path: str | Path) -> list[dict]:
    """Return the transaction log (empty if none exists yet)."""
    path = Path(log_path)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def append_log(
    log_path: str | Path,
    table: str,
    operation: str,
    rows_added: int,
    rows_removed: int,
) -> dict:
    """Append a versioned entry to the transaction log; return the entry."""
    path = Path(log_path)
    entries = read_log(path)
    entry = {
        "version": len(entries) + 1,
        "table": table,
        "operation": operation,
        "rows_added": rows_added,
        "rows_removed": rows_removed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))
    return entry
