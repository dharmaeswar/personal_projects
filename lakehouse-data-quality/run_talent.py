"""Run the talent data-foundations demo: stream + batch ingest, quality checks,
unified model, vended views, and the query-tuning demo.

Writes ``talent_report.txt`` next to this script. All data is synthetic
and seeded; the streaming and batch steps run locally with pandas — no
Spark cluster, Kinesis stream, or Redshift warehouse is involved.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.talent import (
    build_analytics_view,
    build_operational_view,
    build_unified_model,
    check_unified_reconciliation,
    generate_talent,
    generate_talent_events,
    load_learning_batch,
    quarantine_employees,
    quarantine_learning,
    run_talent_stream,
    tune_query_demo,
    validate_employees,
    validate_learning,
)

HERE = Path(__file__).resolve().parent


def main() -> None:
    data = generate_talent()
    lines = ["TALENT DATA FOUNDATIONS REPORT", ""]

    # Streaming ingest of talent change events.
    events = generate_talent_events()
    stream = run_talent_stream(events)
    lines.append(f"stream events arrived: {stream['total_arrived']}")
    lines.append(f"stream events accepted: {len(stream['accepted'])}")
    lines.append(f"stream late dropped: {len(stream['late'])}")
    lines.append(f"stream duplicates dropped: {len(stream['duplicates'])}")
    lines.append(f"stream checkpoint offset: {stream['checkpoint'].last_offset}")
    lines.append("")

    # Batch ingest of learning records.
    loaded, batch_dupes = load_learning_batch(data["learning"])
    lines.append(f"batch learning rows: {len(data['learning'])}")
    lines.append(f"batch learning loaded: {len(loaded)}")
    lines.append(f"batch duplicates dropped: {len(batch_dupes)}")
    lines.append("")

    # Quality checks.
    emp_checks = validate_employees(data["employees"], data["roles"])
    learn_checks = validate_learning(data["learning"], data["employees"], data["skills"])
    lines.append("employee checks:")
    for c in emp_checks:
        lines.append(f"  {c}")
    lines.append("learning checks:")
    for c in learn_checks:
        lines.append(f"  {c}")
    lines.append("")

    silver_learning, quar_learning = quarantine_learning(
        data["learning"], data["employees"], data["skills"]
    )
    silver_employees, quar_employees = quarantine_employees(
        data["employees"], data["roles"]
    )
    lines.append(f"silver employees: {len(silver_employees)}; quarantined: {len(quar_employees)}")
    lines.append(f"silver learning: {len(silver_learning)}; quarantined: {len(quar_learning)}")
    held_back = len(
        silver_learning[
            ~silver_learning["employee_id"].isin(set(silver_employees["employee_id"]))
        ]
    )
    lines.append(
        f"silver learning held back (quarantined employee): {held_back}"
    )
    lines.append("")

    unified = build_unified_model(
        silver_employees,
        data["roles"],
        data["employee_skills"],
        data["skills"],
        silver_learning,
    )
    analytics = build_analytics_view(unified)
    operational = build_operational_view(unified)
    recon = check_unified_reconciliation(unified, silver_learning, analytics)
    lines.append(f"unified talent model rows: {len(unified)}")
    lines.append(f"analytics view rows (departments): {len(analytics)}")
    lines.append(f"operational view rows (employees): {len(operational)}")
    lines.append(f"reconciliation: {recon}")
    for _, row in analytics.iterrows():
        lines.append(
            f"  {row['department']}: headcount {row['headcount']}, "
            f"avg skills {row['avg_skill_count']}, "
            f"avg learning {row['avg_learning_count']}, "
            f"coverage {row['learning_coverage']}"
        )
    lines.append("")

    tuning = tune_query_demo(silver_learning, silver_employees)
    lines.append("query tuning demo:")
    lines.append(f"  rows scanned: {tuning['rows']}; employees: {tuning['employees']}")
    lines.append(f"  per-employee scan loop: {tuning['slow_ms']} ms")
    lines.append(f"  single group-by: {tuning['fast_ms']} ms")
    lines.append(f"  speedup: {tuning['speedup']}x; results match: {tuning['results_match']}")
    lines.append("")

    (HERE / "talent_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
