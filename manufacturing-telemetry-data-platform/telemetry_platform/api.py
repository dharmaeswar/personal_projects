"""Reporting API: the read side of the data platform.

Thin functions over the stores and analytics so a dashboard or a
downstream service asks the platform, not the raw tables.
"""

from __future__ import annotations

import json

from .analytics import daily_report, find_anomalies, machine_summary
from .stores import DataPlatform


def get_machine_summary(platform: DataPlatform, machine_id: str,
                        start: int, end: int) -> dict:
    return machine_summary(platform, machine_id, start, end)


def list_anomalies(platform: DataPlatform, machine_id: str,
                   start: int, end: int) -> list[dict]:
    readings = platform.timeseries.range(machine_id, start, end)
    return [a.__dict__ for a in find_anomalies(readings)]


def get_daily_report(platform: DataPlatform, machine_ids: list[str],
                     start: int, end: int) -> dict:
    return daily_report(platform, machine_ids, start, end)


def latest_reading(platform: DataPlatform, machine_id: str) -> dict | None:
    """Latest reading from the cache store; None if nothing cached."""
    return platform.cache.get(machine_id)


def report_as_json(platform: DataPlatform, machine_ids: list[str],
                   start: int, end: int) -> str:
    return json.dumps(get_daily_report(platform, machine_ids, start, end),
                      indent=2, sort_keys=True)
