"""Incremental loader: reference data, SCD Type 2, and fact loads.

Rules
- Reference feeds (accounts, regions) are upserted (Type 1).
- dim_service is SCD Type 2 on (tier, pricing_model): a changed
  tier/pricing for a service_code closes the current row on the day
  before the change and opens a new row effective on the change date.
  An unchanged re-load opens nothing.
- Fact load is incremental and idempotent: only event_ids not already
  in fact_service_usage are inserted, so re-running the same batch
  inserts 0 rows. Events referencing an unknown account/region are
  quarantined (referential gap), not loaded with a made-up dimension.
- A load_state watermark records the last batch id and max usage date.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .contracts import validate_batch

UNKNOWN_SERVICE_NAME = "Unknown service"


def _date_key(value: str) -> int:
    return int(value.replace("-", ""))


def ensure_date(conn: sqlite3.Connection, value: str) -> int:
    d = date.fromisoformat(value)
    key = _date_key(value)
    conn.execute(
        """INSERT OR IGNORE INTO dim_date
           (date_key, date_value, year, month, day, quarter, weekday, is_weekend)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (key, value, d.year, d.month, d.day, (d.month - 1) // 3 + 1,
         d.weekday(), 1 if d.weekday() >= 5 else 0),
    )
    return key


def upsert_account(conn: sqlite3.Connection, rec: dict) -> int:
    conn.execute(
        """INSERT INTO dim_account (account_id, account_name, account_type, owner_team, created_date)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(account_id) DO UPDATE SET
             account_name=excluded.account_name,
             account_type=excluded.account_type,
             owner_team=excluded.owner_team""",
        (rec["account_id"], rec["account_name"], rec["account_type"],
         rec["owner_team"], rec["created_date"]),
    )
    row = conn.execute(
        "SELECT account_key FROM dim_account WHERE account_id = ?", (rec["account_id"],)
    ).fetchone()
    return row["account_key"]


def upsert_region(conn: sqlite3.Connection, rec: dict) -> int:
    conn.execute(
        """INSERT INTO dim_region (region_code, region_name, country)
           VALUES (?, ?, ?)
           ON CONFLICT(region_code) DO UPDATE SET
             region_name=excluded.region_name, country=excluded.country""",
        (rec["region_code"], rec["region_name"], rec["country"]),
    )
    row = conn.execute(
        "SELECT region_key FROM dim_region WHERE region_code = ?", (rec["region_code"],)
    ).fetchone()
    return row["region_key"]


def upsert_service_scd2(conn: sqlite3.Connection, rec: dict, effective_from: str) -> int:
    """Insert or SCD2-update a service. Returns the current service_key."""
    code = rec["service_code"]
    name = rec.get("service_name") or UNKNOWN_SERVICE_NAME
    tier = rec.get("tier") or "standard"
    pricing = rec.get("pricing_model") or "on-demand"
    current = conn.execute(
        "SELECT * FROM dim_service WHERE service_code = ? AND is_current = 1",
        (code,),
    ).fetchone()
    if current is None:
        cur = conn.execute(
            """INSERT INTO dim_service
               (service_code, service_name, tier, pricing_model, effective_from, effective_to, is_current)
               VALUES (?, ?, ?, ?, ?, NULL, 1)""",
            (code, name, tier, pricing, effective_from),
        )
        return cur.lastrowid
    if current["tier"] == tier and current["pricing_model"] == pricing:
        if current["service_name"] != name:
            conn.execute(
                "UPDATE dim_service SET service_name = ? WHERE service_key = ?",
                (name, current["service_key"]),
            )
        return current["service_key"]
    # Attribute changed: close the old row the day before, open a new one.
    close_date = (date.fromisoformat(effective_from) - timedelta(days=1)).isoformat()
    conn.execute(
        "UPDATE dim_service SET effective_to = ?, is_current = 0 WHERE service_key = ?",
        (close_date, current["service_key"]),
    )
    cur = conn.execute(
        """INSERT INTO dim_service
           (service_code, service_name, tier, pricing_model, effective_from, effective_to, is_current)
           VALUES (?, ?, ?, ?, ?, NULL, 1)""",
        (code, name, tier, pricing, effective_from),
    )
    return cur.lastrowid


def service_key_as_of(conn: sqlite3.Connection, code: str, on_date: str) -> int | None:
    """Service version in force on a usage date (SCD2 point-in-time)."""
    row = conn.execute(
        """SELECT service_key FROM dim_service
           WHERE service_code = ? AND effective_from <= ?
             AND (effective_to IS NULL OR effective_to >= ?)
           ORDER BY effective_from DESC LIMIT 1""",
        (code, on_date, on_date),
    ).fetchone()
    return row["service_key"] if row else None


def load_reference_data(conn: sqlite3.Connection, accounts: list[dict], regions: list[dict]):
    """Validate + upsert reference feeds. Returns (loaded, quarantined)."""
    valid_accts, q_accts = validate_batch("account_metadata", accounts)
    valid_regions, q_regions = validate_batch("region_metadata", regions)
    for rec in valid_accts:
        upsert_account(conn, rec)
    for rec in valid_regions:
        upsert_region(conn, rec)
    conn.commit()
    return {"accounts_loaded": len(valid_accts), "regions_loaded": len(valid_regions)}, q_accts + q_regions


def load_usage_events(conn: sqlite3.Connection, events: list[dict], batch_id: str):
    """Validate, SCD2-maintain services, and incrementally load facts.

    Returns (summary dict, quarantined list). Idempotent: re-running
    the same events inserts 0 new facts.
    """
    valid, quarantined = validate_batch("service_usage_events", events)
    inserted = skipped_duplicate = 0
    max_usage_date = None
    for rec in sorted(valid, key=lambda r: (r["usage_date"], r["event_id"])):
        # Already loaded? Skip — this is what makes re-runs idempotent.
        if conn.execute(
            "SELECT 1 FROM fact_service_usage WHERE event_id = ?", (rec["event_id"],)
        ).fetchone():
            skipped_duplicate += 1
            continue
        account = conn.execute(
            "SELECT account_key FROM dim_account WHERE account_id = ?", (rec["account_id"],)
        ).fetchone()
        region = conn.execute(
            "SELECT region_key FROM dim_region WHERE region_code = ?", (rec["region_code"],)
        ).fetchone()
        if account is None or region is None:
            missing = []
            if account is None:
                missing.append(f"unknown account_id {rec['account_id']}")
            if region is None:
                missing.append(f"unknown region_code {rec['region_code']}")
            quarantined.append({"record": rec, "reasons": missing, "feed": "service_usage_events"})
            continue
        service_key = upsert_service_scd2(conn, rec, rec["usage_date"])
        # Point-in-time lookup: the fact must point at the version in
        # force on the usage date, not just the latest version.
        as_of = service_key_as_of(conn, rec["service_code"], rec["usage_date"])
        service_key = as_of if as_of is not None else service_key
        date_key = ensure_date(conn, rec["usage_date"])
        conn.execute(
            """INSERT INTO fact_service_usage
               (event_id, date_key, service_key, account_key, region_key,
                usage_qty, cost_usd, unit, load_batch_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rec["event_id"], date_key, service_key, account["account_key"],
             region["region_key"], rec["usage_qty"], rec["cost_usd"],
             rec["unit"], batch_id),
        )
        inserted += 1
        if max_usage_date is None or rec["usage_date"] > max_usage_date:
            max_usage_date = rec["usage_date"]
    if max_usage_date:
        conn.execute(
            "INSERT INTO load_state (state_key, value) VALUES ('last_batch_id', ?) "
            "ON CONFLICT(state_key) DO UPDATE SET value=excluded.value",
            (batch_id,),
        )
        conn.execute(
            "INSERT INTO load_state (state_key, value) VALUES ('max_usage_date', ?) "
            "ON CONFLICT(state_key) DO UPDATE SET value=excluded.value",
            (max_usage_date,),
        )
    conn.commit()
    summary = {
        "batch_id": batch_id,
        "events_received": len(events),
        "events_valid": len(valid),
        "facts_inserted": inserted,
        "skipped_duplicates": skipped_duplicate,
        "quarantined": len(quarantined),
        "max_usage_date": max_usage_date,
    }
    return summary, quarantined
