"""Data quality agent: detect, diagnose and help fix warehouse issues.

Perplexity's Data Acceleration work includes data quality agents that
catch problems before they become company-wide: stale loads, volume
collapses, null spikes, duplicate keys and schema drift. This module is
that agent's detection layer, run over a table snapshot (rows already
pulled through the sandbox, never raw table access):

- freshness: last successful load vs the table's SLA.
- volume: row count vs the expected count for the window.
- null rate: share of nulls in a watched column vs a threshold.
- duplicate keys: rows sharing a primary-key value.
- schema drift: columns added, removed or renamed vs the expected schema.

Every finding carries a severity, a likely cause and a recommended fix,
so the agent can open a ticket or page the owner instead of just failing
a check. All data is synthetic and seeded; nothing here is real data.
"""

from __future__ import annotations


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def check_freshness(last_load_day: int, today_day: int,
                    sla_days: int = 1) -> dict | None:
    """Flag a table whose last load is older than its SLA.

    Days are integer day indices (same convention as the sandbox:
    ``created_day`` 0..29 with 29 as today). Returns None when fresh.
    """
    lag = today_day - last_load_day
    if lag <= sla_days:
        return None
    return {
        "type": "stale_load",
        "severity": "critical" if lag > sla_days * 2 else "warning",
        "detail": f"last load {lag} days ago; SLA is {sla_days} day(s)",
        "likely_cause": "upstream job failed, was skipped, or its schedule changed",
        "recommended_fix": "check the upstream job run log, then backfill from the"
                           " last good load before re-enabling downstream models",
    }


def check_volume(row_count: int, expected_rows: int,
                 tolerance: float = 0.20) -> dict | None:
    """Flag a row count far outside the expected range for the window."""
    if expected_rows <= 0:
        return None
    ratio = row_count / expected_rows
    if 1 - tolerance <= ratio <= 1 + tolerance:
        return None
    direction = "drop" if ratio < 1 else "spike"
    return {
        "type": f"volume_{direction}",
        "severity": "critical" if ratio < 0.5 or ratio > 2 else "warning",
        "detail": f"{row_count} rows vs {expected_rows} expected"
                  f" ({ratio:.2f}x)",
        "likely_cause": ("source stopped sending events or a filter silently"
                         " changed" if direction == "drop"
                         else "duplicate ingest, a backfill, or a join fan-out"),
        "recommended_fix": ("compare the source event count for the window"
                            " before trusting the table"
                            if direction == "drop"
                            else "check for duplicate keys and rerun the load"
                                 " with dedup before downstream use"),
    }


def check_null_rate(rows: list[dict], column: str,
                    threshold: float = 0.05) -> dict | None:
    """Flag a watched column whose null share exceeds the threshold."""
    if not rows:
        return None
    nulls = sum(1 for row in rows if row.get(column) is None)
    rate = nulls / len(rows)
    if rate <= threshold:
        return None
    return {
        "type": "null_spike",
        "severity": "critical" if rate > 0.25 else "warning",
        "detail": f"column {column!r}: {nulls}/{len(rows)} null"
                  f" ({rate:.1%}); threshold {threshold:.0%}",
        "likely_cause": "source stopped populating the field or a transform"
                        " started dropping it",
        "recommended_fix": f"quarantine rows with null {column!r}, find the"
                           " first load where the rate jumped, and fix the"
                           " source mapping before backfilling",
    }


def check_duplicates(rows: list[dict], key: str) -> dict | None:
    """Flag rows sharing a primary-key value."""
    seen: set = set()
    dupes = 0
    for row in rows:
        value = row.get(key)
        if value in seen:
            dupes += 1
        seen.add(value)
    if dupes == 0:
        return None
    return {
        "type": "duplicate_keys",
        "severity": "warning",
        "detail": f"{dupes} duplicate row(s) on key {key!r}",
        "likely_cause": "the load ran twice or the source re-sent the same batch",
        "recommended_fix": "deduplicate on the key keeping the latest load,"
                           " then add a uniqueness check to the pipeline",
    }


def check_schema(columns: list[str], expected_columns: list[str]) -> dict | None:
    """Flag columns added, removed or renamed vs the expected schema."""
    added = [c for c in columns if c not in expected_columns]
    removed = [c for c in expected_columns if c not in columns]
    if not added and not removed:
        return None
    return {
        "type": "schema_drift",
        "severity": "critical" if removed else "warning",
        "detail": (f"added: {added or 'none'}; removed: {removed or 'none'}"),
        "likely_cause": "an upstream model or source changed its output"
                        " without a coordinated deploy",
        "recommended_fix": "pin the expected schema in the pipeline, fail"
                           " the load on removed columns, and version the"
                           " model that consumes the new columns",
    }


def run_quality_sweep(snapshot: dict) -> dict:
    """Run every check over one table snapshot and summarise the result.

    Snapshot keys: ``table``, ``today_day``, ``last_load_day``,
    ``sla_days``, ``row_count``, ``expected_rows``, ``columns``,
    ``expected_columns``, ``rows`` (list of dicts), ``key`` (primary key),
    ``null_columns`` (columns to watch, each with an optional threshold
    as ``(name, threshold)`` tuples).
    """
    checks = [
        check_freshness(snapshot["last_load_day"], snapshot["today_day"],
                        snapshot.get("sla_days", 1)),
        check_volume(snapshot["row_count"], snapshot["expected_rows"]),
        check_schema(snapshot["columns"], snapshot["expected_columns"]),
        check_duplicates(snapshot.get("rows", []), snapshot.get("key", "id")),
    ]
    for entry in snapshot.get("null_columns", []):
        column, threshold = entry if isinstance(entry, tuple) else (entry, 0.05)
        checks.append(check_null_rate(snapshot.get("rows", []),
                                      column, threshold))
    issues = [c for c in checks if c is not None]
    worst = "ok"
    if issues:
        worst = max((i["severity"] for i in issues),
                    key=lambda s: SEVERITY_ORDER[s])
    return {
        "table": snapshot["table"],
        "status": "ok" if not issues else worst,
        "issue_count": len(issues),
        "issues": issues,
        "summary": (f"{snapshot['table']}: no issues found"
                    if not issues else
                    f"{snapshot['table']}: {len(issues)} issue(s),"
                    f" worst severity {worst}"),
    }
