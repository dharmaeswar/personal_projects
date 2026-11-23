"""Data observability monitors, in the spirit of Monte Carlo.

Three monitors watch a lakehouse table the way a data-observability
platform would: freshness (is the newest data recent enough?), volume
(is today's row count within its normal band?), and schema drift (did
columns appear or disappear?). Each monitor returns a
:class:`MonitorResult` with a status — ok, warning, or alert — and the
detail a reviewer needs. Monitors never raise on bad data; an alert is
a result, not an error.

All thresholds are explicit arguments with documented defaults, and all
inputs are synthetic. Nothing here is a claim about any real institution.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_FRESHNESS_SLA_MINUTES = 60
DEFAULT_VOLUME_Z_THRESHOLD = 3.0
DEFAULT_VOLUME_WARNING_Z = 2.0


@dataclass
class MonitorResult:
    name: str
    status: str  # "ok", "warning", or "alert"
    detail: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.status.upper()}] {self.name}: {self.detail}"


def check_freshness(
    latest_event_time: pd.Timestamp,
    now: pd.Timestamp,
    sla_minutes: int = DEFAULT_FRESHNESS_SLA_MINUTES,
) -> MonitorResult:
    """Alert if the newest data is older than the freshness SLA."""
    age_minutes = (now - latest_event_time).total_seconds() / 60.0
    if age_minutes <= sla_minutes:
        return MonitorResult(
            "freshness", "ok", f"newest data is {age_minutes:.1f} minutes old (SLA {sla_minutes} minutes)"
        )
    return MonitorResult(
        "freshness",
        "alert",
        f"newest data is {age_minutes:.1f} minutes old, past the {sla_minutes}-minute SLA",
    )


def check_volume(
    current_count: int,
    history_counts: list[int],
    z_threshold: float = DEFAULT_VOLUME_Z_THRESHOLD,
    warning_z: float = DEFAULT_VOLUME_WARNING_Z,
) -> MonitorResult:
    """Alert if today's row count is an outlier against its own history.

    Uses a z-score against the mean and standard deviation of prior
    counts; needs at least 3 history points, otherwise returns ok with
    a note that there is no baseline yet.
    """
    if len(history_counts) < 3:
        return MonitorResult(
            "volume", "ok", f"only {len(history_counts)} history points, no baseline yet"
        )
    history = np.asarray(history_counts, dtype=float)
    mean = float(history.mean())
    std = float(history.std(ddof=1))
    if std == 0:
        status = "ok" if current_count == int(mean) else "alert"
        return MonitorResult("volume", status, f"count {current_count} vs flat baseline {mean:.0f}")
    z = (current_count - mean) / std
    if abs(z) > z_threshold:
        return MonitorResult(
            "volume", "alert", f"count {current_count} is {z:+.2f} std from baseline mean {mean:.1f}"
        )
    if abs(z) > warning_z:
        return MonitorResult(
            "volume", "warning", f"count {current_count} is {z:+.2f} std from baseline mean {mean:.1f}"
        )
    return MonitorResult(
        "volume", "ok", f"count {current_count} is {z:+.2f} std from baseline mean {mean:.1f}"
    )


def check_schema_drift(df: pd.DataFrame, expected_columns: list[str]) -> MonitorResult:
    """Alert on missing columns; warn on unexpected extra columns."""
    actual = set(df.columns)
    expected = set(expected_columns)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        return MonitorResult(
            "schema_drift", "alert", f"missing columns: {', '.join(missing)}"
        )
    if extra:
        return MonitorResult(
            "schema_drift", "warning", f"unexpected columns: {', '.join(extra)}"
        )
    return MonitorResult("schema_drift", "ok", f"schema matches ({len(expected)} columns)")


def run_observability(
    table: pd.DataFrame,
    event_time_column: str,
    now: pd.Timestamp,
    expected_columns: list[str],
    history_counts: list[int],
    sla_minutes: int = DEFAULT_FRESHNESS_SLA_MINUTES,
) -> list[MonitorResult]:
    """Run freshness, volume, and schema-drift monitors on one table."""
    results = []
    if event_time_column in table.columns and len(table):
        latest = pd.to_datetime(table[event_time_column]).max()
        results.append(check_freshness(latest, now, sla_minutes))
    else:
        results.append(
            MonitorResult("freshness", "alert", "no event-time column or empty table")
        )
    results.append(check_volume(len(table), history_counts))
    results.append(check_schema_drift(table, expected_columns))
    return results


def summarize(results: list[MonitorResult]) -> dict:
    """Count monitors by status; the table is healthy only with no alerts."""
    counts = {"ok": 0, "warning": 0, "alert": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return {"counts": counts, "healthy": counts["alert"] == 0}


def render_observability_report(results: list[MonitorResult]) -> str:
    """Render the monitor results as a short plain-text report."""
    lines = ["DATA OBSERVABILITY REPORT", ""]
    for result in results:
        lines.append(str(result))
    lines.append("")
    summary = summarize(results)
    lines.append(f"healthy: {summary['healthy']} (alerts: {summary['counts']['alert']}, warnings: {summary['counts']['warning']})")
    return "\n".join(lines) + "\n"
