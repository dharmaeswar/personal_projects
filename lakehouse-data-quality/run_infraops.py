"""Run the InfraOps analytics demo: stream + batch ingest, quality checks,
unified data-center model, vended views, and the query-tuning demo.

Writes ``infraops_report.txt`` next to this script. All data is synthetic
and seeded; the streaming and batch steps run locally with pandas — no
Spark cluster, Kinesis stream, or Redshift warehouse is involved.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.infraops import (
    build_analytics_view,
    build_operational_view,
    build_unified_model,
    check_unified_reconciliation,
    generate_infraops,
    generate_infraops_events,
    load_incident_batch,
    quarantine_capacity,
    quarantine_equipment,
    quarantine_incidents,
    quarantine_telemetry,
    run_infraops_stream,
    tune_query_demo,
    validate_capacity,
    validate_equipment,
    validate_incidents,
    validate_telemetry,
)

HERE = Path(__file__).resolve().parent


def main() -> None:
    data = generate_infraops()
    lines = ["INFRAOPS ANALYTICS REPORT", ""]

    # Streaming ingest of telemetry change events.
    events = generate_infraops_events()
    stream = run_infraops_stream(events)
    lines.append(f"stream events arrived: {stream['total_arrived']}")
    lines.append(f"stream events accepted: {len(stream['accepted'])}")
    lines.append(f"stream late dropped: {len(stream['late'])}")
    lines.append(f"stream duplicates dropped: {len(stream['duplicates'])}")
    lines.append(f"stream checkpoint offset: {stream['checkpoint'].last_offset}")
    lines.append("")

    # Batch ingest of incidents.
    loaded, batch_dupes = load_incident_batch(data["incidents"])
    lines.append(f"batch incident rows: {len(data['incidents'])}")
    lines.append(f"batch incidents loaded: {len(loaded)}")
    lines.append(f"batch duplicates dropped: {len(batch_dupes)}")
    lines.append("")

    # Quality checks.
    lines.append("telemetry checks:")
    for c in validate_telemetry(data["telemetry"], data["equipment"], data["data_centers"]):
        lines.append(f"  {c}")
    lines.append("incident checks:")
    for c in validate_incidents(data["incidents"], data["data_centers"]):
        lines.append(f"  {c}")
    lines.append("equipment checks:")
    for c in validate_equipment(data["equipment"], data["data_centers"]):
        lines.append(f"  {c}")
    lines.append("capacity checks:")
    for c in validate_capacity(data["capacity"], data["data_centers"]):
        lines.append(f"  {c}")
    lines.append("")

    silver_telemetry, quar_telemetry = quarantine_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    silver_incidents, quar_incidents = quarantine_incidents(
        data["incidents"], data["data_centers"]
    )
    silver_equipment, quar_equipment = quarantine_equipment(
        data["equipment"], data["data_centers"]
    )
    silver_capacity, quar_capacity = quarantine_capacity(
        data["capacity"], data["data_centers"]
    )
    lines.append(f"silver telemetry: {len(silver_telemetry)}; quarantined: {len(quar_telemetry)}")
    lines.append(f"silver incidents: {len(silver_incidents)}; quarantined: {len(quar_incidents)}")
    lines.append(f"silver equipment: {len(silver_equipment)}; quarantined: {len(quar_equipment)}")
    lines.append(f"silver capacity: {len(silver_capacity)}; quarantined: {len(quar_capacity)}")
    lines.append("")

    unified = build_unified_model(
        data["data_centers"],
        silver_telemetry,
        silver_incidents,
        silver_capacity,
    )
    analytics = build_analytics_view(unified)
    operational = build_operational_view(unified)
    recon = check_unified_reconciliation(
        unified, silver_telemetry, silver_incidents, analytics
    )
    lines.append(f"unified infra model rows: {len(unified)}")
    lines.append(f"analytics view rows (regions): {len(analytics)}")
    lines.append(f"operational view rows (data centers): {len(operational)}")
    lines.append(f"reconciliation: {recon}")
    for _, row in analytics.iterrows():
        lines.append(
            f"  {row['region']}: data centers {row['data_centers']}, "
            f"avg temp {row['avg_temp_c']} C, peak utilization {row['peak_utilization_pct']}%, "
            f"incidents {row['incidents']}, avg capacity use {row['avg_capacity_utilization_pct']}%"
        )
    lines.append("")

    tuning = tune_query_demo(silver_telemetry, data["data_centers"])
    lines.append("query tuning demo:")
    lines.append(f"  rows scanned: {tuning['rows']}; data centers: {tuning['data_centers']}")
    lines.append(f"  per-data-center scan loop: {tuning['slow_ms']} ms")
    lines.append(f"  single group-by: {tuning['fast_ms']} ms")
    lines.append(f"  speedup: {tuning['speedup']}x; results match: {tuning['results_match']}")
    lines.append("")

    (HERE / "infraops_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
