"""Run the workforce data-architecture demo: stream + batch ingest, quality
checks, unified hiring-funnel model, vended views, the GenAI-assist
evaluation, and the query-tuning demo.

Writes ``workforce_report.txt`` next to this script. All data is synthetic
and seeded; the streaming and batch steps run locally with pandas — no
Spark cluster, Kinesis stream, or Redshift warehouse is involved, and
no real LLM call is made.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.workforce import (
    build_analytics_view,
    build_operational_view,
    build_unified_model,
    check_unified_reconciliation,
    evaluate_genai_assist,
    generate_workforce,
    generate_workforce_events,
    load_engagement_batch,
    quarantine_candidates,
    quarantine_engagement,
    quarantine_interviews,
    quarantine_moves,
    quarantine_offers,
    run_workforce_stream,
    tune_query_demo,
    validate_candidates,
    validate_engagement,
    validate_interviews,
    validate_moves,
    validate_offers,
)

HERE = Path(__file__).resolve().parent


def main() -> None:
    data = generate_workforce()
    lines = ["WORKFORCE DATA ARCHITECTURE REPORT", ""]

    # Streaming ingest of hiring change events.
    events = generate_workforce_events()
    stream = run_workforce_stream(events)
    lines.append(f"stream events arrived: {stream['total_arrived']}")
    lines.append(f"stream events accepted: {len(stream['accepted'])}")
    lines.append(f"stream late dropped: {len(stream['late'])}")
    lines.append(f"stream duplicates dropped: {len(stream['duplicates'])}")
    lines.append(f"stream checkpoint offset: {stream['checkpoint'].last_offset}")
    lines.append("")

    # Batch ingest of engagement surveys.
    loaded, batch_dupes = load_engagement_batch(data["engagement"])
    lines.append(f"batch engagement rows: {len(data['engagement'])}")
    lines.append(f"batch engagement loaded: {len(loaded)}")
    lines.append(f"batch duplicates dropped: {len(batch_dupes)}")
    lines.append("")

    # Quality checks.
    lines.append("candidate checks:")
    for c in validate_candidates(data["candidates"], data["requisitions"]):
        lines.append(f"  {c}")
    lines.append("interview checks:")
    for c in validate_interviews(data["interviews"], data["candidates"]):
        lines.append(f"  {c}")
    lines.append("offer checks:")
    for c in validate_offers(data["offers"], data["candidates"], data["interviews"]):
        lines.append(f"  {c}")
    lines.append("move checks:")
    for c in validate_moves(data["moves"], data["employees"], data["roles"]):
        lines.append(f"  {c}")
    lines.append("engagement checks:")
    for c in validate_engagement(data["engagement"], data["employees"]):
        lines.append(f"  {c}")
    lines.append("")

    silver_candidates, quar_candidates = quarantine_candidates(
        data["candidates"], data["requisitions"]
    )
    silver_interviews, quar_interviews = quarantine_interviews(
        data["interviews"], data["candidates"]
    )
    silver_offers, quar_offers = quarantine_offers(
        data["offers"], data["candidates"], data["interviews"]
    )
    silver_moves, quar_moves = quarantine_moves(
        data["moves"], data["employees"], data["roles"]
    )
    silver_engagement, quar_engagement = quarantine_engagement(
        data["engagement"], data["employees"]
    )
    lines.append(f"silver candidates: {len(silver_candidates)}; quarantined: {len(quar_candidates)}")
    lines.append(f"silver interviews: {len(silver_interviews)}; quarantined: {len(quar_interviews)}")
    lines.append(f"silver offers: {len(silver_offers)}; quarantined: {len(quar_offers)}")
    lines.append(f"silver moves: {len(silver_moves)}; quarantined: {len(quar_moves)}")
    lines.append(f"silver engagement: {len(silver_engagement)}; quarantined: {len(quar_engagement)}")
    lines.append("")

    unified = build_unified_model(
        data["requisitions"],
        data["roles"],
        silver_candidates,
        silver_interviews,
        silver_offers,
    )
    analytics = build_analytics_view(
        unified, silver_engagement, silver_moves, data["employees"]
    )
    operational = build_operational_view(unified)
    recon = check_unified_reconciliation(unified, silver_candidates, analytics)
    lines.append(f"unified workforce model rows: {len(unified)}")
    lines.append(f"analytics view rows (departments): {len(analytics)}")
    lines.append(f"operational view rows (requisitions): {len(operational)}")
    lines.append(f"reconciliation: {recon}")
    for _, row in analytics.iterrows():
        lines.append(
            f"  {row['department']}: reqs {row['requisitions']}, "
            f"hires {row['hires']}, avg time to fill {row['avg_time_to_fill']}, "
            f"offer-accept {row['offer_accept_rate']}, "
            f"avg engagement {row['avg_engagement']}, moves {row['internal_moves']}"
        )
    lines.append("")

    genai = evaluate_genai_assist()
    lines.append("GenAI-assist evaluation (deterministic stand-in, no real LLM call):")
    lines.append(f"  rules proposed: {genai['rules_proposed']}; true rules: {genai['rules_true']}")
    lines.append(
        f"  violation types caught: {genai['violation_types_caught']}/{genai['violation_types']}"
    )
    lines.append(f"  precision: {genai['precision']}; recall: {genai['recall']}")
    lines.append(f"  spurious rules rejected: {genai['spurious_rules_rejected']}")
    lines.append("")

    tuning = tune_query_demo(silver_candidates, data["requisitions"])
    lines.append("query tuning demo:")
    lines.append(f"  rows scanned: {tuning['rows']}; requisitions: {tuning['requisitions']}")
    lines.append(f"  per-requisition scan loop: {tuning['slow_ms']} ms")
    lines.append(f"  single group-by: {tuning['fast_ms']} ms")
    lines.append(f"  speedup: {tuning['speedup']}x; results match: {tuning['results_match']}")
    lines.append("")

    (HERE / "workforce_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
