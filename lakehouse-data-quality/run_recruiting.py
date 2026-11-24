"""Run the ITA candidate-funnel demo: stream + batch ingest, quality checks,
funnel model, vended views, and reconciliation.

Writes ``recruiting_report.txt`` next to this script. All data is synthetic
and seeded; the streaming and batch steps run locally with pandas — no
Spark cluster, Kinesis stream, or Redshift warehouse is involved.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.recruiting import (
    build_funnel_model,
    build_funnel_view,
    build_requisition_view,
    check_funnel_reconciliation,
    generate_recruiting,
    generate_recruiting_events,
    load_assessment_batch,
    quarantine_applications,
    quarantine_assessments,
    quarantine_hires,
    quarantine_interviews,
    quarantine_offers,
    run_recruiting_stream,
    validate_applications,
    validate_assessments,
    validate_hires,
    validate_interviews,
    validate_offers,
)

HERE = Path(__file__).resolve().parent


def main() -> None:
    data = generate_recruiting()
    lines = ["INTELLIGENT TALENT ACQUISITION — CANDIDATE FUNNEL REPORT", ""]

    # Streaming ingest of funnel events.
    events = generate_recruiting_events()
    stream = run_recruiting_stream(events)
    lines.append(f"stream events arrived: {stream['total_arrived']}")
    lines.append(f"stream events accepted: {len(stream['accepted'])}")
    lines.append(f"stream late dropped: {len(stream['late'])}")
    lines.append(f"stream duplicates dropped: {len(stream['duplicates'])}")
    lines.append(f"stream checkpoint offset: {stream['checkpoint'].last_offset}")
    lines.append("")

    # Batch ingest of online assessments.
    loaded, batch_dupes = load_assessment_batch(data["assessments"])
    lines.append(f"batch assessments rows: {len(data['assessments'])}")
    lines.append(f"batch assessments loaded: {len(loaded)}")
    lines.append(f"batch duplicates dropped: {len(batch_dupes)}")
    lines.append("")

    # Quality checks.
    app_checks = validate_applications(
        data["applications"], data["requisitions"], data["candidates"]
    )
    asm_checks = validate_assessments(data["assessments"], data["applications"])
    int_checks = validate_interviews(data["interviews"], data["applications"])
    ofr_checks = validate_offers(
        data["offers"], data["applications"], data["requisitions"]
    )
    hir_checks = validate_hires(
        data["hires"], data["offers"], data["applications"]
    )
    for label, checks in [
        ("application", app_checks),
        ("assessment", asm_checks),
        ("interview", int_checks),
        ("offer", ofr_checks),
        ("hire", hir_checks),
    ]:
        lines.append(f"{label} checks:")
        for c in checks:
            lines.append(f"  {c}")
    lines.append("")

    silver_app, quar_app = quarantine_applications(
        data["applications"], data["requisitions"], data["candidates"]
    )
    silver_asm, quar_asm = quarantine_assessments(
        data["assessments"], data["applications"]
    )
    silver_int, quar_int = quarantine_interviews(
        data["interviews"], data["applications"]
    )
    silver_ofr, quar_ofr = quarantine_offers(
        data["offers"], data["applications"], data["requisitions"]
    )
    silver_hir, quar_hir = quarantine_hires(
        data["hires"], data["offers"], data["applications"]
    )
    for label, silver, quar in [
        ("applications", silver_app, quar_app),
        ("assessments", silver_asm, quar_asm),
        ("interviews", silver_int, quar_int),
        ("offers", silver_ofr, quar_ofr),
        ("hires", silver_hir, quar_hir),
    ]:
        lines.append(f"silver {label}: {len(silver)}; quarantined: {len(quar)}")
    lines.append("")

    funnel = build_funnel_model(
        silver_app,
        data["requisitions"],
        silver_asm,
        silver_int,
        silver_ofr,
        silver_hir,
    )
    funnel_view = build_funnel_view(funnel)
    req_view = build_requisition_view(funnel, data["requisitions"])
    recon = check_funnel_reconciliation(
        funnel, silver_asm, silver_int, silver_ofr, silver_hir,
        funnel_view, req_view,
    )
    lines.append(f"funnel model rows: {len(funnel)}")
    lines.append(f"funnel view rows (departments): {len(funnel_view)}")
    lines.append(f"requisition view rows: {len(req_view)}")
    lines.append(f"reconciliation: {recon}")
    for _, row in funnel_view.iterrows():
        lines.append(
            f"  {row['department']}: apps {row['applications']}, "
            f"assessed {row['assessed']} ({row['assessment_rate']}), "
            f"interviewed {row['interviewed']}, offered {row['offered']}, "
            f"hired {row['hired']} (overall {row['overall_hire_rate']})"
        )
    lines.append("")
    lines.append("funnel stages:")
    for stage, count in funnel["stage"].value_counts().items():
        lines.append(f"  {stage}: {count}")
    lines.append("")
    median_hire = funnel["days_to_hire"].median()
    lines.append(f"median days to hire: {median_hire}")

    (HERE / "recruiting_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
