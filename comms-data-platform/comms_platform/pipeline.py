"""Comms Data Platform — end-to-end pipeline.

Wires the modules together the way the real platform runs: the Step
Functions-style state machine drives ingest -> validate -> transform ->
catalog -> observe, and each step writes its outputs into the lake,
the catalog, or a report file. Run with `python run_pipeline.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from comms_platform import (
    catalog as catalog_mod,
)
from comms_platform.catalog import Catalog
from comms_platform.connectors import (
    InternalCommsSource,
    VendorAPIClient,
    fetch_all_vendor_metrics,
)
from comms_platform.iac import build_stack, validate_stack
from comms_platform.lake import Lake
from comms_platform.observability import (
    evaluate_alarms,
    orr_checklist,
    run_canaries,
)
from comms_platform.orchestration import StateMachine
from comms_platform.quality import (
    check_messages,
    check_metrics,
    reconcile_gold_to_silver,
)
from comms_platform.transforms import build_daily_engagement


def _step_ingest(ctx):
    lake = ctx["lake"]
    source = InternalCommsSource()
    client = VendorAPIClient()
    messages = pd.DataFrame(source.fetch_messages())
    metrics = pd.DataFrame(fetch_all_vendor_metrics(client))
    lake.write_table("bronze", "messages", messages, operation="ingest")
    lake.write_table("bronze", "metrics", metrics, operation="ingest")
    return {
        "bronze_messages": len(messages),
        "bronze_metrics": len(metrics),
        "vendor_api_calls": client.calls,
    }


def _step_validate(ctx):
    lake = ctx["lake"]
    raw_messages = lake.read_table("bronze", "messages")
    raw_metrics = lake.read_table("bronze", "metrics")
    clean_messages, q_messages = check_messages(raw_messages)
    clean_metrics, q_metrics = check_metrics(raw_metrics)
    lake.write_table("silver", "messages", clean_messages, operation="validate")
    lake.write_table("silver", "metrics", clean_metrics, operation="validate")
    lake.write_table("silver", "messages_quarantine", q_messages, operation="quarantine")
    lake.write_table("silver", "metrics_quarantine", q_metrics, operation="quarantine")
    return {
        "silver_messages": len(clean_messages),
        "silver_metrics": len(clean_metrics),
        "quarantined_messages": len(q_messages),
        "quarantined_metrics": len(q_metrics),
        "quarantine_reasons": sorted(
            set(q_messages["quarantine_reason"].tolist()) | set(q_metrics["quarantine_reason"].tolist())
        ),
    }


def _step_transform(ctx):
    lake = ctx["lake"]
    messages = lake.read_table("silver", "messages")
    metrics = lake.read_table("silver", "metrics")
    gold = build_daily_engagement(messages, metrics)
    lake.write_table("gold", "daily_engagement", gold, operation="transform")
    problems = reconcile_gold_to_silver(gold, messages, metrics)
    return {"gold_rows": len(gold), "reconciliation_problems": problems}


def _step_catalog(ctx):
    lake = ctx["lake"]
    cat = Catalog(ctx["root"] / "catalog.json")
    gold = lake.read_table("gold", "daily_engagement")
    schema = {col: str(dtype) for col, dtype in gold.dtypes.items()}
    try:
        cat.register(
            "daily_engagement",
            "Daily engagement by campaign and channel (gold layer).",
            schema,
            partitions=["event_date"],
            location="s3://comms-data-dev-gold/daily_engagement/",
            owner="comms-tech",
        )
        registered = True
    except ValueError:
        cat.update(
            "daily_engagement",
            schema=schema,
            description="Daily engagement by campaign and channel (gold layer).",
        )
        registered = False
    ctx["catalog"] = cat
    return {"registered": registered, "datasets": cat.list_names()}


def _step_observe(ctx):
    lake = ctx["lake"]
    cat = ctx.get("catalog") or Catalog(ctx["root"] / "catalog.json")
    canaries = run_canaries(lake, cat)
    q_total = 0
    for name in ("messages_quarantine", "metrics_quarantine"):
        if lake.table_exists("silver", name):
            q_total += len(lake.read_table("silver", name))
    alarms = evaluate_alarms(canaries, q_total)
    stack = build_stack("dev")
    stack_problems = validate_stack(stack)
    orr = orr_checklist(canaries, alarms, stack_problems, cat.list_names())
    report = {
        "canaries": canaries,
        "alarms": alarms,
        "stack_problems": stack_problems,
        "orr": orr,
        "orr_passed": all(orr.values()),
    }
    (ctx["root"] / "validation_report.txt").write_text(
        _render_report(report, ctx)
    )
    (ctx["root"] / "observability_report.json").write_text(
        json.dumps(report, indent=2)
    )
    return report


def _render_report(report, ctx):
    lines = ["Comms Data Platform — validation report", ""]
    for c in report["canaries"]:
        lines.append(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail']}")
    lines.append("")
    for a in report["alarms"]:
        lines.append(f"ALARM ({a['severity']}): {a['alarm']} — {a['detail']}")
    if not report["alarms"]:
        lines.append("No alarms.")
    lines.append("")
    lines.append(f"ORR gate: {'PASSED' if report['orr_passed'] else 'FAILED'}")
    for item, passed in report["orr"].items():
        lines.append(f"  [{'x' if passed else ' '}] {item}")
    if report["stack_problems"]:
        lines.append("")
        lines.append("IaC stack problems:")
        lines.extend(f"  - {p}" for p in report["stack_problems"])
    return "\n".join(lines) + "\n"


def run_pipeline(root):
    """Run the full pipeline into `root` (lake, catalog, reports)."""
    root = Path(root)
    ctx = {"root": root, "lake": Lake(root / "lake")}
    machine = StateMachine(
        [
            {"name": "ingest", "fn": _step_ingest, "depends_on": [], "retries": 1},
            {"name": "validate", "fn": _step_validate, "depends_on": ["ingest"], "retries": 1},
            {"name": "transform", "fn": _step_transform, "depends_on": ["validate"], "retries": 1},
            {"name": "catalog", "fn": _step_catalog, "depends_on": ["transform"], "retries": 1},
            {"name": "observe", "fn": _step_observe, "depends_on": ["catalog"], "retries": 0},
        ],
        root / "run_state.json",
    )
    return machine.run("daily", ctx)
