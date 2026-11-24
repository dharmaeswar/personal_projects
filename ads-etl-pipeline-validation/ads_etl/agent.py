"""A deterministic data-operations agent for the ads ETL pipeline.

This module models the agentic-AI pattern the DSP Analytics role works
with — tool use (function calling), a planner that picks tools from
findings, and multi-agent orchestration — as a deterministic,
rule-based simulation. There is no LLM call here: every decision is an
explicit rule over pipeline outputs, so the agent's behaviour is fully
reproducible and every action it proposes is traceable to the evidence
that triggered it. That is the point: an agent that automates the data
operations lifecycle has to be auditable first, clever second.

Three specialist agents share one run context:

- ``ingest-agent`` — owns the bronze layer: runs the quality checks and
  the bronze contract check, and flags ingest problems.
- ``quality-agent`` — owns silver and quarantine: inspects quarantined
  rows, groups them by reason, and proposes a disposition for each group.
- ``governance-agent`` — owns contracts, lineage and backfill: checks
  the silver and gold contracts, verifies lineage coverage, and plans
  any backfill the late-arriving rows require.

The ``Orchestrator`` runs the agents in order, collects their findings,
and produces one ``ActionPlan``: a list of actions with severity, owner,
and the evidence behind each. A clean run produces a plan with no
actions and an explicit "monitor" note, not an empty file.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .checks import CheckResult, run_all_checks
from .contracts import (
    CONTRACTS,
    ContractViolation,
    detect_drift,
    validate_contract,
)


@dataclass
class RunContext:
    """Everything the agents may inspect for one pipeline run."""

    campaigns: list[dict]
    ads: list[dict]
    bronze_events: list[dict]
    silver: list[dict]
    quarantine: list[dict]
    gold: list[dict]
    silver_lineage: list[dict]
    gold_lineage: list[dict]


@dataclass
class ToolCall:
    tool: str
    agent: str
    summary: str
    findings: list[str] = field(default_factory=list)


@dataclass
class Action:
    severity: str  # "block", "fix", or "watch"
    owner: str
    action: str
    evidence: str


@dataclass
class ActionPlan:
    tool_calls: list[ToolCall] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tool_calls": [
                {
                    "tool": c.tool,
                    "agent": c.agent,
                    "summary": c.summary,
                    "findings": c.findings,
                }
                for c in self.tool_calls
            ],
            "actions": [
                {
                    "severity": a.severity,
                    "owner": a.owner,
                    "action": a.action,
                    "evidence": a.evidence,
                }
                for a in self.actions
            ],
        }

    def render_text(self) -> str:
        lines = ["Data-ops agent report", "=====================", ""]
        lines.append("Tool calls:")
        for call in self.tool_calls:
            lines.append(f"- [{call.agent}] {call.tool}: {call.summary}")
            for finding in call.findings:
                lines.append(f"    - {finding}")
        lines.append("")
        if not self.actions:
            lines.append("Actions: none — all checks passed; continue monitoring.")
        else:
            lines.append(f"Actions ({len(self.actions)}):")
            for action in self.actions:
                lines.append(
                    f"- [{action.severity}] ({action.owner}) {action.action}"
                )
                lines.append(f"    evidence: {action.evidence}")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- tools

def tool_run_quality_checks(ctx: RunContext) -> ToolCall:
    results: list[CheckResult] = run_all_checks(
        ctx.bronze_events, ctx.ads, ctx.campaigns
    )
    failed = [r for r in results if not r.passed]
    findings = [str(r) for r in failed] or ["all bronze checks passed"]
    return ToolCall(
        tool="run_quality_checks",
        agent="ingest-agent",
        summary=f"{len(results) - len(failed)} of {len(results)} bronze checks passed",
        findings=findings,
    )


def tool_check_contract(ctx: RunContext, contract_name: str) -> ToolCall:
    contract = CONTRACTS[contract_name]
    table = {
        "events_bronze": ctx.bronze_events,
        "events_silver": ctx.silver,
        "gold_daily_spend": ctx.gold,
    }[contract_name]
    violations: list[ContractViolation] = validate_contract(table, contract)
    drift = detect_drift(table, contract)
    findings = [str(v) for v in violations[:5]]
    if drift["added_columns"]:
        findings.append(f"drift: added columns {drift['added_columns']}")
    if drift["removed_columns"]:
        findings.append(f"drift: removed columns {drift['removed_columns']}")
    if drift["type_changes"]:
        findings.append(f"drift: type changes {drift['type_changes']}")
    if not findings:
        findings = [f"{contract.name} v{contract.version} holds; no drift"]
    return ToolCall(
        tool=f"check_contract:{contract_name}",
        agent="governance-agent",
        summary=(
            f"{len(violations)} contract violations, "
            f"{sum(len(v) for v in drift.values())} drift signals"
        ),
        findings=findings,
    )


def tool_inspect_quarantine(ctx: RunContext) -> ToolCall:
    reasons: Counter = Counter()
    for row in ctx.quarantine:
        for reason in row.get("quarantine_reason", "").split("; "):
            if reason:
                reasons[reason] += 1
    findings = [
        f"{reason}: {count} rows" for reason, count in reasons.most_common()
    ] or ["quarantine is empty"]
    return ToolCall(
        tool="inspect_quarantine",
        agent="quality-agent",
        summary=f"{len(ctx.quarantine)} quarantined rows in "
        f"{len(reasons)} reason groups",
        findings=findings,
    )


def tool_lookup_lineage(ctx: RunContext, event_id: str) -> ToolCall:
    silver_hits = [
        r for r in ctx.silver_lineage if r["silver_event_id"] == event_id
    ]
    gold_hits = [
        g for g in ctx.gold_lineage if event_id in g.get("source_event_ids", [])
    ]
    if silver_hits:
        findings = [
            f"silver event {event_id} <- bronze {silver_hits[0]['bronze_event_id']}",
            f"feeds {len(gold_hits)} gold group(s)",
        ]
    else:
        findings = [f"event {event_id} has no silver lineage (quarantined or absent)"]
    return ToolCall(
        tool="lookup_lineage",
        agent="governance-agent",
        summary=f"lineage for {event_id}: "
        f"{'found' if silver_hits else 'not in silver'}",
        findings=findings,
    )


def tool_plan_backfill(ctx: RunContext) -> ToolCall:
    late = [r for r in ctx.silver if r.get("late_arriving") == 1]
    quarantined_ids = {r["event_id"] for r in ctx.quarantine}
    findings = [
        f"{len(late)} late-arriving rows already in silver (flagged, no backfill needed)",
        f"{len(quarantined_ids)} quarantined rows excluded from gold until fixed",
    ]
    return ToolCall(
        tool="plan_backfill",
        agent="governance-agent",
        summary=f"backfill scope: {len(late)} late rows in silver, "
        f"{len(quarantined_ids)} quarantined rows pending",
        findings=findings,
    )


# ------------------------------------------------------------- agents

@dataclass
class Agent:
    name: str
    role: str
    tools: list[str]  # tool names, in the order the agent calls them


AGENTS: list[Agent] = [
    Agent(
        name="ingest-agent",
        role="bronze layer: quality checks and bronze contract",
        tools=["run_quality_checks", "check_contract:events_bronze"],
    ),
    Agent(
        name="quality-agent",
        role="silver layer: quarantine triage and disposition",
        tools=["inspect_quarantine"],
    ),
    Agent(
        name="governance-agent",
        role="contracts, lineage and backfill planning",
        tools=[
            "check_contract:events_silver",
            "check_contract:gold_daily_spend",
            "plan_backfill",
        ],
    ),
]


class Orchestrator:
    """Run the agents in order and turn findings into one action plan."""

    def __init__(self, agents: list[Agent] | None = None):
        self.agents = agents if agents is not None else AGENTS

    def run(self, ctx: RunContext) -> ActionPlan:
        plan = ActionPlan()
        failed_checks = 0
        contract_violations = 0
        for agent in self.agents:
            for tool_name in agent.tools:
                if tool_name == "run_quality_checks":
                    call = tool_run_quality_checks(ctx)
                    failed_checks += sum(
                        1
                        for f in call.findings
                        if f.startswith("[FAIL]")
                    )
                elif tool_name.startswith("check_contract:"):
                    call = tool_check_contract(
                        ctx, tool_name.split(":", 1)[1]
                    )
                    contract_violations += len(
                        [f for f in call.findings if f.startswith("[")]
                    )
                elif tool_name == "inspect_quarantine":
                    call = tool_inspect_quarantine(ctx)
                elif tool_name == "plan_backfill":
                    call = tool_plan_backfill(ctx)
                else:  # pragma: no cover - registry is closed
                    raise ValueError(f"unknown tool: {tool_name}")
                plan.tool_calls.append(call)

        # Planner rules: findings -> actions, each with its evidence.
        if failed_checks:
            plan.actions.append(
                Action(
                    severity="block",
                    owner="dsp-analytics-ingest",
                    action=(
                        "Hold the silver build until the failing bronze "
                        "checks are triaged; do not promote bad rows."
                    ),
                    evidence=f"{failed_checks} bronze quality checks failed",
                )
            )
        if contract_violations:
            plan.actions.append(
                Action(
                    severity="block",
                    owner="dsp-analytics-platform",
                    action=(
                        "Freeze the affected table and open a contract "
                        "review with the table owner before the next load."
                    ),
                    evidence=f"{contract_violations} contract violations found",
                )
            )
        if ctx.quarantine:
            top_reason = Counter(
                r
                for row in ctx.quarantine
                for r in row.get("quarantine_reason", "").split("; ")
                if r
            ).most_common(1)[0]
            plan.actions.append(
                Action(
                    severity="fix",
                    owner="dsp-analytics-platform",
                    action=(
                        "Fix the top quarantine cause at the source and "
                        "replay the affected events through silver."
                    ),
                    evidence=(
                        f"{len(ctx.quarantine)} rows quarantined; top cause "
                        f"'{top_reason[0]}' ({top_reason[1]} rows)"
                    ),
                )
            )
        late = sum(1 for r in ctx.silver if r.get("late_arriving") == 1)
        if late:
            plan.actions.append(
                Action(
                    severity="watch",
                    owner="dsp-analytics-platform",
                    action=(
                        "Confirm the next gold rebuild picked up the "
                        "late-arriving rows already flagged in silver."
                    ),
                    evidence=f"{late} late-arriving rows in silver",
                )
            )
        return plan
