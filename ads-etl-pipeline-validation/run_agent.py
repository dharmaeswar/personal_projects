"""Run the pipeline once, then run the data-ops agent over the result.

Usage: python run_agent.py
Writes agent_report.json and agent_report.txt in the project root.
The pipeline itself runs in an in-memory SQLite database, so this
script never touches ads_tables/ or the validation report.
"""

from __future__ import annotations

import json
from pathlib import Path

from ads_etl.agent import Orchestrator, RunContext, tool_lookup_lineage
from ads_etl.data import generate_all
from ads_etl.pipeline import build_gold, build_silver, connect, load_bronze
from ads_etl.streaming import EventConsumer, consume_all_in_batches


def main() -> None:
    root = Path(__file__).resolve().parent
    data = generate_all()
    campaigns, ads, bronze_events = data["campaigns"], data["ads"], data["events"]

    consumer = EventConsumer()
    consumer.produce(bronze_events)
    ingested = consume_all_in_batches(consumer, batch_size=100)

    conn = connect(":memory:")
    load_bronze(conn, campaigns, ads, ingested)
    silver, quarantine, silver_lineage = build_silver(
        conn, ingested, ads, campaigns
    )
    gold, gold_lineage = build_gold(conn, silver)
    conn.close()

    ctx = RunContext(
        campaigns=campaigns,
        ads=ads,
        bronze_events=ingested,
        silver=silver,
        quarantine=quarantine,
        gold=gold,
        silver_lineage=silver_lineage,
        gold_lineage=gold_lineage,
    )

    plan = Orchestrator().run(ctx)
    # Demonstrate lineage lookup on a real silver event, as the
    # governance agent would when a downstream team asks "where did
    # this number come from?".
    first_event = silver[0]["event_id"]
    plan.tool_calls.append(tool_lookup_lineage(ctx, first_event))

    report = {
        "bronze_rows": len(ingested),
        "silver_rows": len(silver),
        "quarantine_rows": len(quarantine),
        "gold_groups": len(gold),
        "plan": plan.to_dict(),
    }
    (root / "agent_report.json").write_text(json.dumps(report, indent=2))
    (root / "agent_report.txt").write_text(plan.render_text())
    print(plan.render_text())
    print(f"lineage demo: {first_event}")
    print(f"actions planned: {len(plan.actions)}")


if __name__ == "__main__":
    main()
