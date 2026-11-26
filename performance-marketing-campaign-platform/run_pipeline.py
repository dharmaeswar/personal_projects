"""End-to-end run: ingest -> plan -> pace -> quality -> warehouse -> summary.

Builds the campaign plan for five synthetic campaigns across the five ad
platforms, ingests 14 days of delivery, checks pacing and optimisation
guardrails, runs data-quality checks, writes the bronze/silver/gold
medallion, and drafts the LLM-assist summary (always human-gated).

Usage: python run_pipeline.py [--out output]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from campaign_platform import ai_assist, ingest, orchestration, pacing, planning, quality, warehouse

CAMPAIGNS = [
    {"campaign_id": "cmp_prada2_search", "platform": "google_ads",
     "total_budget": 140_000.0, "flight_start": "2026-10-01",
     "flight_end": "2026-10-14", "target_cpa": 42.0, "target_reach": 4_200_000},
    {"campaign_id": "cmp_prada2_social", "platform": "meta",
     "total_budget": 98_000.0, "flight_start": "2026-10-01",
     "flight_end": "2026-10-14", "target_cpa": 38.0, "target_reach": 3_100_000},
    {"campaign_id": "cmp_wish_display", "platform": "dv360",
     "total_budget": 84_000.0, "flight_start": "2026-10-01",
     "flight_end": "2026-10-14", "target_cpa": 55.0, "target_reach": 2_600_000},
    {"campaign_id": "cmp_wish_video", "platform": "trade_desk",
     "total_budget": 70_000.0, "flight_start": "2026-10-01",
     "flight_end": "2026-10-14", "target_cpa": 48.0, "target_reach": 1_900_000},
    {"campaign_id": "cmp_festival_native", "platform": "yahoo",
     "total_budget": 42_000.0, "flight_start": "2026-10-01",
     "flight_end": "2026-10-14", "target_cpa": 30.0, "target_reach": 900_000},
]


def build_context(out_dir: Path) -> dict:
    return {"out_dir": out_dir, "campaigns": CAMPAIGNS,
            "plan": planning.build_plan(CAMPAIGNS)}


def step_ingest(ctx: dict) -> None:
    frames, quarantined = [], 0
    for platform in ingest.PLATFORMS:
        ids = [c["campaign_id"] for c in ctx["campaigns"] if c["platform"] == platform]
        plan_row = next(r for r in ctx["plan"] if r["platform"] == platform)
        rows = ingest.generate_platform_rows(
            platform, ids, daily_budget=plan_row["daily_budget"])
        valid, bad = ingest.validate_contract(rows, platform)
        quarantined += len(bad)
        frames.append(ingest.normalize(valid, platform))
    ctx["raw"] = pd.concat(frames, ignore_index=True)
    ctx["raw"] = ingest.dedupe(ctx["raw"])
    ctx["contract_quarantined"] = quarantined


def step_plan_pace(ctx: dict) -> None:
    gold_by_campaign = ctx["raw"].groupby("campaign_id")["spend"].sum().to_dict()
    pacing_results, guardrails, findings = [], [], []
    for row in ctx["plan"]:
        actual = gold_by_campaign.get(row["campaign_id"], 0.0)
        result = pacing.pacing_status(row, actual, day_index=14)
        pacing_results.append(result)
        if result["status"] != "on-track":
            findings.append({"kind": "pacing", "campaign_id": row["campaign_id"],
                             "detail": f"{result['status']}: variance {result['variance_pct']}%"})
        day = ctx["raw"][ctx["raw"]["campaign_id"] == row["campaign_id"]].iloc[-1]
        decision = pacing.optimisation_guardrails(row, {
            "spend": float(day["spend"]), "conversions": float(day["conversions"]),
            "impressions": int(day["impressions"]), "clicks": int(day["clicks"])})
        guardrails.append(decision)
        if decision["decision"] == "HOLD":
            findings.append({"kind": "guardrail", "campaign_id": row["campaign_id"],
                             "decision": "HOLD",
                             "detail": "; ".join(decision["reasons"])})
    ctx["pacing"] = pacing_results
    ctx["guardrails"] = guardrails
    ctx["findings"] = findings


def step_quality(ctx: dict) -> None:
    campaign_ids = {c["campaign_id"] for c in ctx["campaigns"]}
    ctx["checks"] = quality.run_checks(ctx["raw"], campaign_ids)
    clean, quarantined = quality.quarantine(ctx["raw"], campaign_ids)
    ctx["clean"] = clean
    ctx["quality_quarantined"] = len(quarantined)
    failed = [c for c in ctx["checks"] if not c["passed"]]
    for check in failed:
        ctx["findings"].append({"kind": "quality", "campaign_id": "all",
                                "detail": f"{check['check']}: {check['detail']}"})


def step_warehouse(ctx: dict) -> None:
    ctx["medallion"] = warehouse.write_medallion(ctx["raw"], ctx["clean"], ctx["out_dir"])
    ctx["dim"] = warehouse.build_campaign_dim(ctx["campaigns"])


def step_summary(ctx: dict) -> None:
    draft = ai_assist.summarize_findings(ctx["findings"])
    ctx["draft"] = draft
    ctx["evaluation"] = ai_assist.evaluate_summary(draft, ctx["findings"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = build_context(out_dir)
    tasks = [
        orchestration.DagTask("ingest", step_ingest),
        orchestration.DagTask("plan_pace", step_plan_pace, ("ingest",)),
        orchestration.DagTask("quality", step_quality, ("ingest",)),
        orchestration.DagTask("warehouse", step_warehouse, ("quality",)),
        orchestration.DagTask("summary", step_summary, ("plan_pace", "quality")),
    ]
    result = orchestration.run_dag(tasks, ctx)
    report = {
        "dag": result,
        "plan_campaigns": len(ctx["plan"]),
        "raw_rows": len(ctx["raw"]),
        "contract_quarantined": ctx["contract_quarantined"],
        "quality_quarantined": ctx["quality_quarantined"],
        "medallion": ctx["medallion"],
        "pacing": ctx["pacing"],
        "guardrails": ctx["guardrails"],
        "checks": ctx["checks"],
        "summary_draft": ctx["draft"],
        "summary_evaluation": ctx["evaluation"],
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    lines = [
        "# Performance Marketing Campaign Platform — run report",
        "",
        f"- Campaigns planned: {len(ctx['plan'])} across {len(ingest.PLATFORMS)} platforms",
        f"- Raw rows ingested: {len(ctx['raw'])} "
        f"({ctx['contract_quarantined']} quarantined at contract)",
        f"- Quality quarantined: {ctx['quality_quarantined']} rows",
        f"- Medallion: bronze {ctx['medallion']['bronze_rows']} / "
        f"silver {ctx['medallion']['silver_rows']} / gold {ctx['medallion']['gold_rows']} rows",
        f"- Pacing: {', '.join(p['campaign_id'] + '=' + p['status'] for p in ctx['pacing'])}",
        f"- Guardrails: {sum(1 for g in ctx['guardrails'] if g['decision'] == 'ALLOW')} ALLOW / "
        f"{sum(1 for g in ctx['guardrails'] if g['decision'] == 'HOLD')} HOLD",
        f"- Summary evaluation passed: {ctx['evaluation']['passed']} "
        f"(score {ctx['evaluation']['score']}, human review required)",
        "",
        "## Summary draft (human review required before any live change)",
        "",
        ctx["draft"]["summary"],
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
