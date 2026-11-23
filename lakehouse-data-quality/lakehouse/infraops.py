"""Central InfraOps analytics: data-center infrastructure operations data.

An Amazon Central InfraOps Analytics Data Engineer builds the data
foundation behind AWS's global data-center operations: ETL pipelines
that ingest infrastructure signals into the warehouse and lake, data
models that drive physical design, quality measures and monitoring
that keep the data trusted. This module models that flow with
synthetic, seeded data (no real facility or company data anywhere):

- **Streaming ingest** — telemetry change events (power, temperature,
  humidity, utilization readings) arrive as micro-batches and are
  processed exactly once by reusing
  :func:`lakehouse.streaming.run_stream`: dedup on ``event_id``
  against a checkpoint, late events dropped at the watermark. In
  production this is Kinesis / FireHose into Redshift; here it runs
  locally with pandas, and the code says so.
- **Batch ingest** — a nightly incident batch, deduplicated on
  ``incident_id`` (keep first), the way a Glue ETL job would load it.
- **Unified infra model** — one row per data center: telemetry
  aggregates (average temperature, maximum utilization, total power),
  incident counts and capacity utilization. Built only from clean
  (silver) rows.
- **Vended views** — an analytics view (per region: data centers,
  average temperature, peak utilization, incidents, capacity use) and
  an operational view (one row per data center: health signals and
  status) for downstream dashboards and APIs.
- **Quality checks** — completeness, uniqueness, value ranges,
  referential integrity, plus three infra rules: no incident may
  resolve before it opened, no equipment may be decommissioned
  before it was installed, and every telemetry row must name the
  data center its equipment belongs to. Bad rows are quarantined
  with a reason, never dropped silently.
- **Query tuning** — an inefficient per-data-center scan loop versus
  a single grouped aggregation, with measured wall times.

The fixture plants 8 bad rows on purpose so the checks have real
violations to catch:

- 2 duplicate telemetry ``reading_id`` values
- 1 null ``dc_id`` on a telemetry row
- 1 telemetry row for unknown equipment (EQ-999)
- 1 temperature reading of 52 C (valid range is 10-45 C)
- 1 utilization reading of 112% (valid range is 0-100%)
- 1 incident resolved before it opened
- 1 equipment decommissioned before it was installed
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .checks import (
    CheckResult,
    check_completeness,
    check_ranges,
    check_referential_integrity,
    check_uniqueness,
)
from .streaming import run_stream

REGIONS = ["us-east", "us-west", "eu-west", "ap-south"]
EQUIP_TYPES = ["server", "cooling", "power", "network"]
METRICS = ["power_kw", "temp_c", "humidity_pct", "utilization_pct"]

# Valid ranges per telemetry metric.
METRIC_RANGES = {
    "power_kw": (0, 5000),
    "temp_c": (10, 45),
    "humidity_pct": (0, 100),
    "utilization_pct": (0, 100),
}

N_DATA_CENTERS = 8
N_EQUIPMENT_BASE = 60
N_TELEMETRY_BASE = 240
N_INCIDENTS_BASE = 24
N_CAPACITY_DAYS = 30


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_data_centers(seed: int = 42) -> pd.DataFrame:
    """8 synthetic data centers across 4 regions."""
    rng = _rng(seed + 30)
    return pd.DataFrame(
        {
            "dc_id": [f"DC-{101 + i}" for i in range(N_DATA_CENTERS)],
            "region": [REGIONS[i % len(REGIONS)] for i in range(N_DATA_CENTERS)],
            "capacity_mw": [int(v) for v in rng.integers(20, 120, size=N_DATA_CENTERS)],
            "opened_date": pd.to_datetime(
                rng.integers(
                    pd.Timestamp("2022-01-01").value,
                    pd.Timestamp("2025-06-30").value,
                    size=N_DATA_CENTERS,
                )
            ),
        }
    )


def generate_equipment(
    data_centers: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """60 synthetic equipment items, each installed in one data center."""
    rng = _rng(seed + 31)
    dc_ids = data_centers["dc_id"].tolist()
    opened_by_dc = data_centers.set_index("dc_id")["opened_date"]
    rows = []
    for i in range(N_EQUIPMENT_BASE):
        dc = str(rng.choice(dc_ids))
        install = opened_by_dc.loc[dc] + pd.Timedelta(days=int(rng.integers(0, 600)))
        decom = install + pd.Timedelta(days=int(rng.integers(200, 900)))
        rows.append(
            {
                "equip_id": f"EQ-{2001 + i}",
                "dc_id": dc,
                "equip_type": str(rng.choice(EQUIP_TYPES)),
                "install_date": install,
                "decommission_date": (
                    decom if rng.random() < 0.3 else pd.NaT
                ),
                "status": str(rng.choice(["active", "active", "active", "retired"])),
            }
        )
    return pd.DataFrame(rows)


def _metric_value(metric: str, rng: np.random.Generator) -> float:
    if metric == "power_kw":
        return round(float(rng.uniform(200, 4200)), 1)
    if metric == "temp_c":
        return round(float(rng.uniform(18, 32)), 1)
    if metric == "humidity_pct":
        return round(float(rng.uniform(30, 70)), 1)
    return round(float(rng.uniform(20, 95)), 1)


def generate_telemetry(
    equipment: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """240 synthetic telemetry readings over Nov 17-23, 2026."""
    rng = _rng(seed + 32)
    dc_by_equip = equipment.set_index("equip_id")["dc_id"]
    base = pd.Timestamp("2026-11-17 00:00", tz="UTC")
    rows = []
    for i in range(N_TELEMETRY_BASE):
        equip = str(rng.choice(equipment["equip_id"].tolist()))
        metric = str(rng.choice(METRICS))
        rows.append(
            {
                "reading_id": f"RD-{3001 + i}",
                "equip_id": equip,
                "dc_id": dc_by_equip.loc[equip],
                "metric": metric,
                "value": _metric_value(metric, rng),
                "ts": base + pd.Timedelta(minutes=int(rng.integers(0, 7 * 24 * 60))),
            }
        )
    return pd.DataFrame(rows)


def generate_incidents(
    data_centers: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """24 synthetic incidents, each opened and (usually) resolved."""
    rng = _rng(seed + 33)
    dc_ids = data_centers["dc_id"].tolist()
    base = pd.Timestamp("2026-11-01")
    rows = []
    for i in range(N_INCIDENTS_BASE):
        opened = base + pd.Timedelta(days=int(rng.integers(0, 22)), hours=int(rng.integers(0, 24)))
        rows.append(
            {
                "incident_id": f"INC-{4001 + i}",
                "dc_id": str(rng.choice(dc_ids)),
                "severity": str(rng.choice(["sev1", "sev2", "sev3", "sev4"])),
                "opened_at": opened,
                "resolved_at": (
                    opened + pd.Timedelta(hours=int(rng.integers(1, 72)))
                    if rng.random() < 0.85
                    else pd.NaT
                ),
                "status": str(rng.choice(["resolved", "resolved", "open"])),
            }
        )
    return pd.DataFrame(rows)


def generate_capacity(
    data_centers: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """Daily capacity snapshots: 8 data centers x 30 days."""
    rng = _rng(seed + 34)
    rows = []
    for _, dc in data_centers.iterrows():
        for day in range(N_CAPACITY_DAYS):
            rows.append(
                {
                    "dc_id": dc["dc_id"],
                    "date": pd.Timestamp("2026-10-25") + pd.Timedelta(days=day),
                    "utilized_mw": round(
                        float(dc["capacity_mw"] * rng.uniform(0.45, 0.85)), 1
                    ),
                    "capacity_mw": int(dc["capacity_mw"]),
                }
            )
    return pd.DataFrame(rows)


def plant_violations(
    telemetry: pd.DataFrame,
    incidents: pd.DataFrame,
    equipment: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Plant 8 bad rows: 5 bad telemetry rows, 1 bad incident, 1 bad
    equipment row. Returns copies."""
    telemetry = telemetry.copy()
    incidents = incidents.copy()
    equipment = equipment.copy()
    # 2 duplicate telemetry reading_ids (copies of rows 0 and 1).
    dup = telemetry.iloc[[0, 1]].copy()
    telemetry = pd.concat([telemetry, dup], ignore_index=True)
    # 1 null dc_id.
    telemetry.loc[telemetry.index[2], "dc_id"] = None
    # 1 telemetry row for unknown equipment.
    telemetry.loc[telemetry.index[3], "equip_id"] = "EQ-999"
    # 1 temperature reading of 52 C (rows 0-3 already carry other
    # violations, so pick a clean row).
    temp_idx = telemetry[
        (telemetry["metric"] == "temp_c") & (telemetry.index >= 4)
    ].index[0]
    telemetry.loc[temp_idx, "value"] = 52.0
    # 1 utilization reading of 112%.
    util_idx = telemetry[
        (telemetry["metric"] == "utilization_pct") & (telemetry.index >= 4)
    ].index[0]
    telemetry.loc[util_idx, "value"] = 112.0
    # 1 incident resolved before it opened.
    incidents.loc[incidents.index[0], "resolved_at"] = (
        incidents.loc[incidents.index[0], "opened_at"] - pd.Timedelta(hours=5)
    )
    # 1 equipment decommissioned before it was installed.
    equipment.loc[equipment.index[0], "decommission_date"] = (
        equipment.loc[equipment.index[0], "install_date"] - pd.Timedelta(days=30)
    )
    return telemetry, incidents, equipment


def generate_infraops(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Seeded InfraOps domains with the 8 planted violations."""
    data_centers = generate_data_centers(seed)
    equipment = generate_equipment(data_centers, seed)
    telemetry = generate_telemetry(equipment, seed)
    incidents = generate_incidents(data_centers, seed)
    capacity = generate_capacity(data_centers, seed)
    telemetry, incidents, equipment = plant_violations(
        telemetry, incidents, equipment
    )
    return {
        "data_centers": data_centers,
        "equipment": equipment,
        "telemetry": telemetry,
        "incidents": incidents,
        "capacity": capacity,
    }


def check_metric_ranges(telemetry: pd.DataFrame) -> CheckResult:
    """Fail if any telemetry value falls outside its metric's range."""
    failing: list[int] = []
    for idx, row in telemetry.iterrows():
        low, high = METRIC_RANGES[row["metric"]]
        if not (low <= row["value"] <= high):
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "metric_ranges", True, "all telemetry values in range"
        )
    return CheckResult(
        "metric_ranges",
        False,
        f"{len(failing)} telemetry values outside range",
        failing,
    )


def check_incident_after_open(incidents: pd.DataFrame) -> CheckResult:
    """Fail if any incident resolved before it opened."""
    failing: list[int] = []
    for idx, row in incidents.iterrows():
        if pd.notna(row["resolved_at"]) and row["resolved_at"] < row["opened_at"]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "incident_after_open", True, "all incidents resolve after opening"
        )
    return CheckResult(
        "incident_after_open",
        False,
        f"{len(failing)} incidents resolved before opening",
        failing,
    )


def check_decommission_after_install(equipment: pd.DataFrame) -> CheckResult:
    """Fail if any equipment was decommissioned before it was installed."""
    failing: list[int] = []
    for idx, row in equipment.iterrows():
        if pd.notna(row["decommission_date"]) and row["decommission_date"] < row["install_date"]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "decommission_after_install",
            True,
            "all equipment decommissioned after installation",
        )
    return CheckResult(
        "decommission_after_install",
        False,
        f"{len(failing)} equipment decommissioned before installation",
        failing,
    )


def check_telemetry_dc_matches_equipment(
    telemetry: pd.DataFrame, equipment: pd.DataFrame
) -> CheckResult:
    """Fail if a telemetry row names a different data center than its equipment."""
    dc_by_equip = equipment.set_index("equip_id")["dc_id"]
    failing: list[int] = []
    for idx, row in telemetry.iterrows():
        if pd.isna(row["equip_id"]) or row["equip_id"] not in dc_by_equip.index:
            continue  # completeness / referential checks own those rows
        if pd.notna(row["dc_id"]) and row["dc_id"] != dc_by_equip.loc[row["equip_id"]]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "telemetry_dc_matches_equipment",
            True,
            "all telemetry rows match their equipment data center",
        )
    return CheckResult(
        "telemetry_dc_matches_equipment",
        False,
        f"{len(failing)} telemetry rows in the wrong data center",
        failing,
    )


def validate_telemetry(
    telemetry: pd.DataFrame,
    equipment: pd.DataFrame,
    data_centers: pd.DataFrame,
) -> list[CheckResult]:
    """Completeness, uniqueness, ranges, references, DC-match rule."""
    return [
        check_completeness(telemetry, ["reading_id", "equip_id", "dc_id", "value"]),
        check_uniqueness(telemetry, "reading_id"),
        check_referential_integrity(telemetry, "equip_id", equipment, "equip_id"),
        check_referential_integrity(telemetry, "dc_id", data_centers, "dc_id"),
        check_metric_ranges(telemetry),
        check_telemetry_dc_matches_equipment(telemetry, equipment),
    ]


def validate_incidents(
    incidents: pd.DataFrame, data_centers: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness, DC reference, open/resolve rule."""
    return [
        check_completeness(incidents, ["incident_id", "dc_id", "opened_at"]),
        check_uniqueness(incidents, "incident_id"),
        check_referential_integrity(incidents, "dc_id", data_centers, "dc_id"),
        check_incident_after_open(incidents),
    ]


def validate_equipment(
    equipment: pd.DataFrame, data_centers: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness, DC reference, install/decommission rule."""
    return [
        check_completeness(equipment, ["equip_id", "dc_id", "install_date"]),
        check_uniqueness(equipment, "equip_id"),
        check_referential_integrity(equipment, "dc_id", data_centers, "dc_id"),
        check_decommission_after_install(equipment),
    ]


def validate_capacity(
    capacity: pd.DataFrame, data_centers: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, DC reference, utilization range.

    No single-column uniqueness check: the natural key is
    (dc_id, date), and the quarantine step dedups on that pair.
    """
    return [
        check_completeness(capacity, ["dc_id", "date", "utilized_mw"]),
        check_referential_integrity(capacity, "dc_id", data_centers, "dc_id"),
        check_ranges(capacity, "utilized_mw", 0, None),
    ]


def _quarantine(
    frame: pd.DataFrame, checks: list[CheckResult], key: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a frame into silver (clean) and quarantine (failed, with reason).

    A row fails if it trips any check. Duplicate keys keep only the
    first occurrence in silver.
    """
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=frame.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = frame.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = frame.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=[key], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def quarantine_telemetry(
    telemetry: pd.DataFrame,
    equipment: pd.DataFrame,
    data_centers: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(
        telemetry, validate_telemetry(telemetry, equipment, data_centers), "reading_id"
    )


def quarantine_incidents(
    incidents: pd.DataFrame, data_centers: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(
        incidents, validate_incidents(incidents, data_centers), "incident_id"
    )


def quarantine_equipment(
    equipment: pd.DataFrame, data_centers: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(
        equipment, validate_equipment(equipment, data_centers), "equip_id"
    )


def quarantine_capacity(
    capacity: pd.DataFrame, data_centers: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Capacity has one row per (dc_id, date); dedup on the pair, not dc_id.
    checks = validate_capacity(capacity, data_centers)
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=capacity.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = capacity.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = capacity.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=["dc_id", "date"], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def build_unified_model(
    silver_data_centers: pd.DataFrame,
    silver_telemetry: pd.DataFrame,
    silver_incidents: pd.DataFrame,
    silver_capacity: pd.DataFrame,
) -> pd.DataFrame:
    """Health signals per data center: one row per clean data center.

    Telemetry aggregates (average temperature, maximum utilization,
    total power), incident counts and latest capacity utilization.
    Built only from silver rows.
    """
    tele = silver_telemetry.copy()
    temp = tele[tele["metric"] == "temp_c"].groupby("dc_id", as_index=False).agg(
        avg_temp_c=("value", "mean")
    )
    util = tele[tele["metric"] == "utilization_pct"].groupby("dc_id", as_index=False).agg(
        max_utilization_pct=("value", "max")
    )
    power = tele[tele["metric"] == "power_kw"].groupby("dc_id", as_index=False).agg(
        total_power_kw=("value", "sum"),
        power_readings=("value", "count"),
    )
    inc = silver_incidents.groupby("dc_id", as_index=False).agg(
        incidents=("incident_id", "count"),
        sev1_incidents=("severity", lambda s: int((s == "sev1").sum())),
    )
    latest_cap = (
        silver_capacity.sort_values("date")
        .groupby("dc_id", as_index=False)
        .tail(1)[["dc_id", "utilized_mw", "capacity_mw"]]
    )
    latest_cap["capacity_utilization_pct"] = (
        latest_cap["utilized_mw"] / latest_cap["capacity_mw"] * 100
    ).round(1)
    unified = silver_data_centers.merge(temp, on="dc_id", how="left")
    unified = unified.merge(util, on="dc_id", how="left")
    unified = unified.merge(power, on="dc_id", how="left")
    unified = unified.merge(inc, on="dc_id", how="left")
    unified = unified.merge(
        latest_cap[["dc_id", "capacity_utilization_pct"]], on="dc_id", how="left"
    )
    unified["avg_temp_c"] = unified["avg_temp_c"].round(1)
    for col in ["incidents", "sev1_incidents", "power_readings"]:
        unified[col] = unified[col].fillna(0).astype("int64")
    unified["total_power_kw"] = unified["total_power_kw"].fillna(0).round(1)
    return unified.sort_values("dc_id").reset_index(drop=True)


def build_analytics_view(unified: pd.DataFrame) -> pd.DataFrame:
    """Gold analytics view: one row per region.

    Data centers, average temperature, peak utilization, incidents and
    average capacity utilization — the numbers an InfraOps team would
    chart for capacity planning.
    """
    view = (
        unified.groupby("region", as_index=False)
        .agg(
            data_centers=("dc_id", "count"),
            avg_temp_c=("avg_temp_c", "mean"),
            peak_utilization_pct=("max_utilization_pct", "max"),
            incidents=("incidents", "sum"),
            avg_capacity_utilization_pct=("capacity_utilization_pct", "mean"),
        )
    )
    view["avg_temp_c"] = view["avg_temp_c"].round(1)
    view["avg_capacity_utilization_pct"] = view["avg_capacity_utilization_pct"].round(1)
    return view.sort_values("region").reset_index(drop=True)


def build_operational_view(unified: pd.DataFrame) -> pd.DataFrame:
    """Gold operational view: one row per data center, for dashboards and APIs.

    Current health signals and status — the fields a technician or
    site leader reads to decide where a data center stands.
    """
    return unified[
        [
            "dc_id",
            "region",
            "avg_temp_c",
            "max_utilization_pct",
            "total_power_kw",
            "incidents",
            "sev1_incidents",
            "capacity_utilization_pct",
        ]
    ].copy()


def check_unified_reconciliation(
    unified: pd.DataFrame,
    silver_telemetry: pd.DataFrame,
    silver_incidents: pd.DataFrame,
    analytics_view: pd.DataFrame,
) -> CheckResult:
    """Fail if the vended views disagree with the unified model or silver."""
    vendable_tele = silver_telemetry[
        silver_telemetry["dc_id"].isin(set(unified["dc_id"]))
    ]
    vendable_inc = silver_incidents[
        silver_incidents["dc_id"].isin(set(unified["dc_id"]))
    ]
    problems = []
    if int(unified["power_readings"].sum()) != len(
        vendable_tele[vendable_tele["metric"] == "power_kw"]
    ):
        problems.append("unified power readings do not sum to silver power rows")
    if int(unified["incidents"].sum()) != len(vendable_inc):
        problems.append("unified incidents do not sum to silver incidents")
    if int(analytics_view["data_centers"].sum()) != len(unified):
        problems.append("analytics data centers do not sum to unified rows")
    if int(analytics_view["incidents"].sum()) != int(unified["incidents"].sum()):
        problems.append("analytics incidents do not match unified model")
    if problems:
        return CheckResult("infraops_reconciliation", False, "; ".join(problems))
    return CheckResult(
        "infraops_reconciliation",
        True,
        f"views reconcile: {len(unified)} data centers, "
        f"{len(vendable_tele)} vendable telemetry rows",
    )


def generate_infraops_events(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Synthetic telemetry change-event stream with planted late events and duplicates.

    120 events: 3 are duplicate deliveries of earlier event ids, 2 arrive
    with an event time older than the watermark will allow (late data).
    Duplicates are re-delivered in a later micro-batch than their
    originals, so the exactly-once dedup sees them as re-deliveries.
    Each event names its metric and the data center it concerns, the
    way a telemetry log event would.
    """
    from datetime import datetime, timedelta, timezone

    rng = _rng(seed + 35)
    base = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    event_times = [base + timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)]
    event_times.sort()
    df = pd.DataFrame(
        {
            "offset": list(range(n)),
            "event_id": [f"I{i:05d}" for i in range(n)],
            "event_time": pd.to_datetime(event_times, utc=True),
            "ingested_at": pd.to_datetime(
                [t + timedelta(seconds=int(s)) for t, s in zip(event_times, rng.integers(5, 120, size=n))],
                utc=True,
            ),
            "metric": rng.choice(METRICS, size=n),
            "dc_id": [f"DC-{101 + int(i)}" for i in rng.integers(0, 8, size=n)],
            "event_type": rng.choice(["reading", "alert", "resolved"], size=n),
        }
    )
    dupes = df.iloc[[5, 40, 90]].copy()
    dupes["offset"] = [n, n + 1, n + 2]
    late = df.iloc[[10, 60]].copy()
    late["event_id"] = ["I90001", "I90002"]
    late["offset"] = [n + 3, n + 4]
    late["event_time"] = pd.to_datetime(
        [base - timedelta(hours=3), base - timedelta(hours=2, minutes=30)], utc=True
    )
    stream = pd.concat([df, dupes, late], ignore_index=True)
    return stream.sort_values("offset").reset_index(drop=True)


def run_infraops_stream(events: pd.DataFrame) -> dict:
    """Process the telemetry event stream exactly once via the shared streamer."""
    return run_stream(events)


def load_incident_batch(
    incidents: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nightly batch load: dedup on incident_id, keep first; return (loaded, duplicates)."""
    dup_mask = incidents.duplicated(subset=["incident_id"], keep="first")
    duplicates = incidents.loc[dup_mask].copy().reset_index(drop=True)
    loaded = incidents.loc[~dup_mask].copy().reset_index(drop=True)
    return loaded, duplicates


def tune_query_demo(
    silver_telemetry: pd.DataFrame, silver_data_centers: pd.DataFrame
) -> dict:
    """Inefficient query vs tuned query, with measured wall times.

    Slow query (the anti-pattern): for each data center, scan the whole
    telemetry table to compute that data center's average temperature
    — one full pass per data center, the way a row-by-row lookup
    behaves.
    Tuned query: a single group-by aggregation over the same data.
    Both must return identical per-data-center averages. The demo tiles
    the telemetry table to at least 50k rows so the difference is
    measurable; the tiling only repeats seeded rows with new reading
    ids, so the averages are unchanged.
    """
    import math

    reps = max(1, math.ceil(50000 / max(len(silver_telemetry), 1)))
    big = pd.concat([silver_telemetry] * reps, ignore_index=True)
    big["reading_id"] = [f"RD-{90000 + i}" for i in range(len(big))]
    temp = big[big["metric"] == "temp_c"]
    dc_ids = silver_data_centers["dc_id"].tolist()

    start = time.perf_counter()
    slow = {}
    for dc in dc_ids:
        subset = temp[temp["dc_id"] == dc]
        slow[dc] = round(float(subset["value"].mean()), 4) if len(subset) else None
    slow_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    grouped = temp.groupby("dc_id")["value"].mean().round(4)
    fast_ms = (time.perf_counter() - start) * 1000
    fast = {dc: (None if dc not in grouped.index else float(grouped.loc[dc])) for dc in dc_ids}

    matches = all(
        (slow[d] is None and fast[d] is None)
        or (slow[d] is not None and fast[d] is not None and abs(slow[d] - fast[d]) < 0.001)
        for d in dc_ids
    )
    return {
        "rows": len(big),
        "data_centers": len(dc_ids),
        "slow_ms": round(slow_ms, 1),
        "fast_ms": round(fast_ms, 1),
        "speedup": round(slow_ms / fast_ms, 1) if fast_ms > 0 else float("inf"),
        "results_match": matches,
    }
