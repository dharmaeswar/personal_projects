"""Analytics and reporting over stored telemetry.

Rollups per machine and run, anomaly flags with plain-language reasons,
and a daily report a reviewer can read without opening a database.
All inputs are the seeded synthetic readings in this repo.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .stores import DataPlatform, TelemetryReading

TEMP_LIMIT_C = 950.0
VIBRATION_LIMIT_MM_S = 12.0
WELD_CURRENT_BAND_A = (180.0, 320.0)


@dataclass(frozen=True)
class Anomaly:
    machine_id: str
    ts: int
    kind: str
    severity: str
    reason: str


def machine_summary(platform: DataPlatform, machine_id: str,
                    start: int, end: int) -> dict:
    readings = platform.timeseries.range(machine_id, start, end)
    if not readings:
        return {"machine_id": machine_id, "readings": 0}
    temps = [r.temp_c for r in readings]
    vibs = [r.vibration_mm_s for r in readings]
    currents = [r.weld_current_a for r in readings]
    return {
        "machine_id": machine_id,
        "readings": len(readings),
        "layers": sorted({r.layer for r in readings}),
        "mean_temp_c": round(statistics.fmean(temps), 2),
        "max_temp_c": max(temps),
        "mean_vibration_mm_s": round(statistics.fmean(vibs), 3),
        "max_vibration_mm_s": max(vibs),
        "mean_weld_current_a": round(statistics.fmean(currents), 1),
        "statuses": sorted({r.status for r in readings}),
    }


def _zscore(value: float, values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def find_anomalies(readings: list[TelemetryReading]) -> list[Anomaly]:
    """Flag out-of-limit readings; each finding cites its own record."""
    anomalies: list[Anomaly] = []
    temps = [r.temp_c for r in readings]
    vibs = [r.vibration_mm_s for r in readings]
    for reading in readings:
        if reading.temp_c > TEMP_LIMIT_C:
            anomalies.append(Anomaly(
                reading.machine_id, reading.ts, "over_temperature",
                "high",
                f"temp {reading.temp_c:.1f}C above limit {TEMP_LIMIT_C:.0f}C"
                f" at layer {reading.layer}",
            ))
        if reading.vibration_mm_s > VIBRATION_LIMIT_MM_S:
            anomalies.append(Anomaly(
                reading.machine_id, reading.ts, "vibration_spike",
                "high",
                f"vibration {reading.vibration_mm_s:.2f} mm/s above limit"
                f" {VIBRATION_LIMIT_MM_S:.0f} mm/s at layer {reading.layer}",
            ))
        if not (WELD_CURRENT_BAND_A[0] <= reading.weld_current_a
                <= WELD_CURRENT_BAND_A[1]):
            anomalies.append(Anomaly(
                reading.machine_id, reading.ts, "weld_current_out_of_band",
                "medium",
                f"weld current {reading.weld_current_a:.1f}A outside band"
                f" {WELD_CURRENT_BAND_A[0]:.0f}-{WELD_CURRENT_BAND_A[1]:.0f}A",
            ))
        if abs(_zscore(reading.temp_c, temps)) >= 3.0:
            anomalies.append(Anomaly(
                reading.machine_id, reading.ts, "temperature_outlier",
                "medium",
                f"temp {reading.temp_c:.1f}C is 3+ std devs from the run mean",
            ))
    anomalies.sort(key=lambda a: (a.ts, a.kind))
    return anomalies


def daily_report(platform: DataPlatform, machine_ids: list[str],
                 start: int, end: int) -> dict:
    """One report dict: per-machine summaries plus every anomaly."""
    summaries = [machine_summary(platform, mid, start, end)
                 for mid in machine_ids]
    all_anomalies: list[Anomaly] = []
    for mid in machine_ids:
        all_anomalies.extend(
            find_anomalies(platform.timeseries.range(mid, start, end)))
    by_kind: dict[str, int] = {}
    for anomaly in all_anomalies:
        by_kind[anomaly.kind] = by_kind.get(anomaly.kind, 0) + 1
    return {
        "machines": summaries,
        "anomaly_count": len(all_anomalies),
        "anomalies_by_kind": by_kind,
        "anomalies": [a.__dict__ for a in all_anomalies],
    }
