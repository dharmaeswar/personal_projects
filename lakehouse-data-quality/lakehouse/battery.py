"""Battery-telemetry module for the lakehouse: cell-cycling time-series data.

This extends the lakehouse with the data a battery energy-storage team
lives on: high-volume time-series samples from cell-cycling tests in the
lab and from fleet batteries in the field. It mirrors the same medallion
pattern as the orders pipeline — bronze ingest, quality checks, silver
clean tables, gold aggregates — with the checks a sensor pipeline needs:

- **Schema conformance** — every sample must match the telemetry contract
  (battery, cell, lab, timestamp, cycle, voltage, current, temperature,
  state of charge) before it is trusted downstream.
- **Completeness / uniqueness** — null readings and duplicate
  (cell, timestamp) samples are quarantined, never dropped silently.
- **Ranges** — voltage, current, temperature and state of charge must sit
  inside the physical limits of a lithium-ion cell.
- **Monotonic timestamps** — samples must arrive in time order per cell;
  a late sample is flagged, not silently re-sorted.
- **Sample gaps** — a gap longer than the 10-minute sampling interval
  means the feed dropped samples; the gap is reported with the count of
  missing samples so a scientist knows the series is incomplete.
- **Lineage** — bronze, silver and gold are written with
  :func:`lakehouse.pipeline.write_table`, so every table carries a
  Delta-style transaction log (version, operation, rows added/removed).

All telemetry is synthetic and seeded. Nothing here is a claim about any
real battery, lab, or fleet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .checks import CheckResult
from .pipeline import read_log, write_table
from .schema import ColumnSpec, TableSchema, cast_to_schema, enforce_schema

# Sampling: one sample every 10 minutes for 48 hours per cell.
SAMPLE_INTERVAL_MINUTES = 10
N_SAMPLES_PER_CELL = 288  # 48 hours at 10-minute intervals
START = datetime(2026, 11, 1, 0, 0, 0)  # naive, like the rest of the lakehouse

BATTERIES = ["B001", "B002", "B003", "B004", "B005", "B006"]
CELLS_PER_BATTERY = 4
LABS = {
    "B001": "Boston",
    "B002": "Irvine",
    "B003": "Sunnyvale",
    "B004": "Seattle",
    "B005": "Boston",
    "B006": "Irvine",
}

# Physical limits for a lithium-ion cell under test (the data contract).
VOLTAGE_MIN, VOLTAGE_MAX = 2.5, 4.2
CURRENT_MIN, CURRENT_MAX = -50.0, 50.0
TEMPERATURE_MIN, TEMPERATURE_MAX = -20.0, 60.0
SOC_MIN, SOC_MAX = 0.0, 100.0

# Dropped samples: (cell_id, sample positions) removed from the series,
# so the gap check has real gaps to find: 3 missing in B002-C2, 1 in B004-C1.
DROPPED_SAMPLES = {
    "B002-C2": (100, 101, 102),
    "B004-C1": (200,),
}

# (cell_id, sample position, column, bad value) planted violations.
PLANTED_VIOLATIONS = {
    "duplicate_sample": 3,
    "null_temperature": 4,
    "voltage_out_of_range": 2,
    "temperature_out_of_range": 2,
    "state_of_charge_out_of_range": 1,
    "late_sample": 1,
}


@dataclass
class TelemetryViolation:
    cell_id: str
    position: int
    column: str
    value: object


BATTERY_TELEMETRY_SCHEMA = TableSchema(
    "battery_telemetry",
    [
        ColumnSpec("battery_id", "string", nullable=False),
        ColumnSpec("cell_id", "string", nullable=False),
        ColumnSpec("test_lab", "string", nullable=False),
        ColumnSpec("timestamp", "datetime64[ns]", nullable=False),
        ColumnSpec("cycle_number", "int64", nullable=False),
        ColumnSpec("voltage_v", "float64", nullable=False),
        ColumnSpec("current_a", "float64", nullable=False),
        ColumnSpec("temperature_c", "float64", nullable=False),
        ColumnSpec("state_of_charge", "float64", nullable=False),
    ],
)

GOLD_BATTERY_SCHEMA = TableSchema(
    "daily_battery_summary",
    [
        ColumnSpec("battery_id", "string", nullable=False),
        ColumnSpec("summary_date", "datetime64[ns]", nullable=False),
        ColumnSpec("sample_count", "int64", nullable=False),
        ColumnSpec("cycles_observed", "int64", nullable=False),
        ColumnSpec("mean_voltage_v", "float64", nullable=False),
        ColumnSpec("max_temperature_c", "float64", nullable=False),
        ColumnSpec("min_state_of_charge", "float64", nullable=False),
    ],
)


def _rng(seed: int = 11) -> np.random.Generator:
    return np.random.default_rng(seed)


def _at(position: int) -> pd.Timestamp:
    return pd.Timestamp(START + timedelta(minutes=SAMPLE_INTERVAL_MINUTES * position))


def generate_clean_telemetry(seed: int = 11) -> pd.DataFrame:
    """Seeded synthetic cell-cycling telemetry, no violations planted.

    Six batteries x four cells, one sample every 10 minutes for 48 hours.
    Voltage, current, temperature and state of charge follow one charge /
    discharge cycle every 4 hours (24 samples), with small seeded noise.
    """
    rng = _rng(seed)
    rows = []
    for battery in BATTERIES:
        for cell in range(1, CELLS_PER_BATTERY + 1):
            cell_id = f"{battery}-C{cell}"
            dropped = DROPPED_SAMPLES.get(cell_id, ())
            for pos in range(N_SAMPLES_PER_CELL):
                if pos in dropped:
                    continue  # feed dropped these samples; the gap check finds them
                phase = 2 * np.pi * (pos % 24) / 24
                rows.append(
                    {
                        "battery_id": battery,
                        "cell_id": cell_id,
                        "test_lab": LABS[battery],
                        "timestamp": _at(pos),
                        "cycle_number": pos // 24 + 1,
                        "voltage_v": round(
                            float(
                                np.clip(
                                    3.6 + 0.6 * np.sin(phase) + rng.normal(0, 0.02),
                                    2.6,
                                    4.15,
                                )
                            ),
                            3,
                        ),
                        "current_a": round(
                            25.0 * np.cos(phase) + rng.normal(0, 1.0), 2
                        ),
                        "temperature_c": round(
                            28.0 + 6.0 * np.sin(phase + 0.5) + rng.normal(0, 0.5), 2
                        ),
                        "state_of_charge": round(
                            float(np.clip(60.0 + 40.0 * np.sin(phase - np.pi / 2)
                                          + rng.normal(0, 0.5), 0, 100)),
                            2,
                        ),
                    }
                )
    return pd.DataFrame(rows)


def plant_telemetry_violations(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``telemetry`` with 13 planted bad rows + 1 late sample.

    - 3 duplicate samples (same cell + timestamp, appended at the end)
    - 4 null temperatures
    - 2 voltages outside 2.5-4.2 V, 2 temperatures outside -20-60 C
    - 1 state of charge above 100
    - 1 late sample: the timestamps of two adjacent samples in one cell
      are swapped, so the second sample lands before the first in file
      order while the sorted series stays gap-free
    """
    bad = telemetry.copy()

    def _row(cell_id: str, position: int) -> int:
        matches = bad.index[
            (bad["cell_id"] == cell_id) & (bad["timestamp"] == _at(position))
        ]
        assert len(matches) == 1, f"expected one row for {cell_id}@{position}"
        return int(matches[0])

    # 3 duplicate samples, appended at the end like a redelivered feed batch.
    dupes = bad.loc[
        [
            _row("B001-C1", 10),
            _row("B003-C3", 50),
            _row("B005-C4", 80),
        ]
    ]
    bad = pd.concat([bad, dupes], ignore_index=True)
    # 4 null temperatures.
    for cell_id, pos in (
        ("B001-C2", 20),
        ("B002-C1", 30),
        ("B004-C3", 40),
        ("B006-C4", 60),
    ):
        bad.loc[_row(cell_id, pos), "temperature_c"] = None
    # 2 voltages outside the cell's physical limits.
    bad.loc[_row("B002-C2", 70), "voltage_v"] = 5.1
    bad.loc[_row("B003-C1", 90), "voltage_v"] = 1.8
    # 2 temperatures outside the cell's physical limits.
    bad.loc[_row("B004-C2", 110), "temperature_c"] = 85.0
    bad.loc[_row("B005-C1", 120), "temperature_c"] = -30.0
    # 1 state of charge above 100.
    bad.loc[_row("B006-C2", 130), "state_of_charge"] = 104.0
    # 1 late sample: swap the timestamps of two adjacent samples in
    # B001-C1, so the second lands before the first in file order.
    first = _row("B001-C1", 150)
    second = _row("B001-C1", 151)
    bad.loc[first, "timestamp"], bad.loc[second, "timestamp"] = (
        bad.loc[second, "timestamp"],
        bad.loc[first, "timestamp"],
    )
    return bad


def generate_telemetry(seed: int = 11) -> pd.DataFrame:
    """Seeded bronze telemetry: clean series plus the planted violations."""
    return plant_telemetry_violations(generate_clean_telemetry(seed))


def _deduplicate(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Drop redelivered samples, keeping the first (cell_id, timestamp)."""
    return telemetry.drop_duplicates(
        subset=["cell_id", "timestamp"], keep="first"
    )


def check_telemetry_completeness(telemetry: pd.DataFrame) -> CheckResult:
    """Fail if any reading column holds nulls; report the null count."""
    parts = []
    failing: set[int] = set()
    for col in ("voltage_v", "current_a", "temperature_c", "state_of_charge"):
        n = int(telemetry[col].isna().sum())
        if n:
            parts.append(f"{col}: {n} nulls")
            failing.update(telemetry.index[telemetry[col].isna()].tolist())
    if not parts:
        return CheckResult(
            "telemetry completeness", True, "no nulls in reading columns"
        )
    return CheckResult(
        "telemetry completeness", False, "; ".join(parts), sorted(failing)
    )


def check_telemetry_uniqueness(telemetry: pd.DataFrame) -> CheckResult:
    """Fail if any (cell_id, timestamp) pair repeats; report the extra rows."""
    dup_mask = telemetry.duplicated(subset=["cell_id", "timestamp"], keep="first")
    n = int(dup_mask.sum())
    if n == 0:
        return CheckResult(
            "telemetry uniqueness",
            True,
            f"all {len(telemetry)} (cell_id, timestamp) pairs unique",
        )
    return CheckResult(
        "telemetry uniqueness",
        False,
        f"{n} duplicate (cell_id, timestamp) samples",
        sorted(telemetry.index[dup_mask].tolist()),
    )


def check_telemetry_ranges(telemetry: pd.DataFrame) -> list[CheckResult]:
    """Fail if any reading falls outside the cell's physical limits."""
    results = []
    for column, low, high, unit in (
        ("voltage_v", VOLTAGE_MIN, VOLTAGE_MAX, "V"),
        ("current_a", CURRENT_MIN, CURRENT_MAX, "A"),
        ("temperature_c", TEMPERATURE_MIN, TEMPERATURE_MAX, "C"),
        ("state_of_charge", SOC_MIN, SOC_MAX, "%"),
    ):
        mask = telemetry[column].notna() & (
            (telemetry[column] < low) | (telemetry[column] > high)
        )
        n = int(mask.sum())
        if n == 0:
            results.append(
                CheckResult(
                    f"telemetry range:{column}",
                    True,
                    f"all {column} values within [{low}, {high}] {unit}",
                )
            )
        else:
            results.append(
                CheckResult(
                    f"telemetry range:{column}",
                    False,
                    f"{n} rows with {column} outside [{low}, {high}] {unit}",
                    sorted(telemetry.index[mask].tolist()),
                )
            )
    return results


def check_timestamp_monotonic(telemetry: pd.DataFrame) -> CheckResult:
    """Fail if any cell's samples are out of time order (expects deduped input).

    Flags the row whose timestamp is at or before the previous sample in
    the same cell's file order — a late-arriving sample, not a bad reading.
    """
    failing: list[int] = []
    for _, group in telemetry.groupby("cell_id", sort=False):
        prev = None
        for idx, ts in zip(group.index, group["timestamp"]):
            if prev is not None and ts <= prev:
                failing.append(int(idx))
            prev = ts
    if not failing:
        return CheckResult(
            "telemetry monotonic timestamps",
            True,
            "timestamps increase within every cell's series",
        )
    return CheckResult(
        "telemetry monotonic timestamps",
        False,
        f"{len(failing)} samples out of time order",
        sorted(failing),
    )


def check_sample_gaps(
    telemetry: pd.DataFrame, expected_minutes: int = SAMPLE_INTERVAL_MINUTES
) -> CheckResult:
    """Fail if any cell's series has a gap longer than the sampling interval.

    A gap means the feed dropped samples; the detail reports how many
    samples are missing so a scientist knows the series is incomplete.
    """
    gaps = 0
    missing = 0
    for _, group in telemetry.groupby("cell_id", sort=False):
        stamps = group["timestamp"].sort_values()
        diffs = stamps.diff().dt.total_seconds().div(60).dropna()
        for diff in diffs:
            if diff > expected_minutes * 1.5:
                gaps += 1
                missing += int(round(diff / expected_minutes)) - 1
    if gaps == 0:
        return CheckResult(
            "telemetry sample gaps",
            True,
            f"no gaps longer than {expected_minutes} minutes in any cell",
        )
    return CheckResult(
        "telemetry sample gaps",
        False,
        f"{gaps} gaps, {missing} samples missing from the feed",
    )


def run_battery_checks(telemetry: pd.DataFrame) -> list[CheckResult]:
    """Run the full bronze check suite on telemetry (dedup before ordering)."""
    deduped = _deduplicate(telemetry)
    return [
        check_telemetry_completeness(telemetry),
        check_telemetry_uniqueness(telemetry),
        *check_telemetry_ranges(telemetry),
        check_timestamp_monotonic(deduped),
        check_sample_gaps(deduped),
    ]


def build_battery_silver(
    telemetry: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean bronze telemetry into silver + quarantine.

    Silver keeps only rows that pass every row-level check, deduplicated
    and typed to the telemetry schema. Quarantine holds the rejected rows
    with a ``quarantine_reason`` column. Gaps are absences, not rows, so
    they are reported by the gap check and never quarantined.
    """
    deduped = _deduplicate(telemetry)
    reasons: dict[int, list[str]] = {}
    for label, result in [
        ("null reading", check_telemetry_completeness(telemetry)),
        ("duplicate sample", check_telemetry_uniqueness(telemetry)),
        *(
            (f"{column} out of range", r)
            for column, r in zip(
                ("voltage_v", "current_a", "temperature_c", "state_of_charge"),
                check_telemetry_ranges(telemetry),
            )
        ),
        ("out of time order", check_timestamp_monotonic(deduped)),
    ]:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(label)
    mask = pd.Series(False, index=telemetry.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = telemetry.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = telemetry.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=["cell_id", "timestamp"], keep="first")
    silver = cast_to_schema(silver, BATTERY_TELEMETRY_SCHEMA)
    silver = silver.reset_index(drop=True)
    quarantine = quarantine.reset_index(drop=True)
    return silver, quarantine


def build_battery_gold(silver: pd.DataFrame) -> pd.DataFrame:
    """Aggregate silver telemetry into a daily summary per battery."""
    frame = silver.copy()
    frame["summary_date"] = frame["timestamp"].dt.normalize()
    gold = (
        frame.groupby(["battery_id", "summary_date"], as_index=False)
        .agg(
            sample_count=("cell_id", "count"),
            cycles_observed=("cycle_number", "nunique"),
            mean_voltage_v=("voltage_v", "mean"),
            max_temperature_c=("temperature_c", "max"),
            min_state_of_charge=("state_of_charge", "min"),
        )
    )
    gold["mean_voltage_v"] = gold["mean_voltage_v"].round(3)
    gold = cast_to_schema(gold, GOLD_BATTERY_SCHEMA)
    return gold.sort_values(["battery_id", "summary_date"]).reset_index(drop=True)


def check_battery_reconciliation(
    silver: pd.DataFrame, gold: pd.DataFrame
) -> CheckResult:
    """Fail if gold sample counts do not add back up to the silver rows."""
    expected = int(len(silver))
    got = int(gold["sample_count"].sum())
    if got == expected:
        return CheckResult(
            "battery reconciliation",
            True,
            f"gold sample counts sum to all {expected} silver rows",
        )
    return CheckResult(
        "battery reconciliation",
        False,
        f"gold sums to {got} samples but silver holds {expected}",
    )


def run_battery_telemetry(out_dir: str | Path) -> dict:
    """Run the full battery-telemetry pipeline; return a summary dict.

    Writes bronze / silver / gold Parquet tables (each with a Delta-style
    log) under ``out_dir`` and returns row counts, check results and the
    reconciliation verdict.
    """
    out = Path(out_dir)
    bronze = generate_telemetry()
    entry = write_table(bronze, out / "bronze" / "battery_telemetry",
                        "bronze ingest (battery_telemetry)")
    bronze_version = entry["version"]

    results = run_battery_checks(bronze)
    silver, quarantine = build_battery_silver(bronze)
    entry = write_table(silver, out / "silver" / "battery_telemetry",
                        "silver clean")
    silver_version = entry["version"]
    entry = write_table(quarantine, out / "silver" / "quarantine",
                        "silver quarantine")
    quarantine_version = entry["version"]

    gold = build_battery_gold(silver)
    entry = write_table(gold, out / "gold" / "daily_battery_summary",
                        "gold aggregate")
    gold_version = entry["version"]

    silver_violations = enforce_schema(silver, BATTERY_TELEMETRY_SCHEMA)
    gold_violations = enforce_schema(gold, GOLD_BATTERY_SCHEMA)
    reconciliation = check_battery_reconciliation(silver, gold)
    return {
        "bronze_rows": len(bronze),
        "silver_rows": len(silver),
        "quarantine_rows": len(quarantine),
        "gold_groups": len(gold),
        "checks": results,
        "checks_failed": sum(1 for r in results if not r.passed),
        "reconciliation": reconciliation,
        "silver_schema_violations": silver_violations,
        "gold_schema_violations": gold_violations,
        "log_versions": {
            "bronze": bronze_version,
            "silver": silver_version,
            "quarantine": quarantine_version,
            "gold": gold_version,
        },
    }
