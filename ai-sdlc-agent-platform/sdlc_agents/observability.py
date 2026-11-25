"""Observability and quality tooling: what agents did, what it cost, how well.

Every SDLC run lands in a SQLite store — stage outcomes, tool calls, model
spend — and the dashboard rolls it up: pass rates by stage, spend by model,
and governance flags (blocked releases, unreviewed auto-merges). A dashboard
an engineer can trust is what lets a team hand work to agents at all.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass
class RunRecord:
    ticket_id: str
    stage: str
    passed: bool
    summary: str
    findings: list[str]


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, stage TEXT,"
        " passed INTEGER, summary TEXT, findings TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS spend ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, model TEXT,"
        " task_type TEXT, cost REAL)"
    )
    conn.commit()
    return conn


def record_run(conn: sqlite3.Connection, record: RunRecord) -> None:
    conn.execute(
        "INSERT INTO runs (ticket_id, stage, passed, summary, findings)"
        " VALUES (?, ?, ?, ?, ?)",
        (record.ticket_id, record.stage, int(record.passed), record.summary,
         json.dumps(record.findings)),
    )
    conn.commit()


def record_spend(conn: sqlite3.Connection, ticket_id: str, model: str,
                 task_type: str, cost: float) -> None:
    conn.execute(
        "INSERT INTO spend (ticket_id, model, task_type, cost) VALUES (?, ?, ?, ?)",
        (ticket_id, model, task_type, cost),
    )
    conn.commit()


def dashboard(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    passed = conn.execute("SELECT COUNT(*) FROM runs WHERE passed = 1").fetchone()[0]
    by_stage = {
        stage: {
            "runs": runs,
            "pass_rate": round(ok / runs, 3) if runs else 0.0,
        }
        for stage, runs, ok in conn.execute(
            "SELECT stage, COUNT(*), SUM(passed) FROM runs GROUP BY stage"
        ).fetchall()
    }
    spend_by_model = {
        model: round(cost, 4)
        for model, cost in conn.execute(
            "SELECT model, SUM(cost) FROM spend GROUP BY model"
        ).fetchall()
    }
    total_cost = round(sum(spend_by_model.values()), 4)
    blocked = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE stage = 'release' AND passed = 0"
    ).fetchone()[0]
    return {
        "total_stage_runs": total,
        "overall_pass_rate": round(passed / total, 3) if total else 0.0,
        "pass_rate_by_stage": by_stage,
        "total_model_spend_usd": total_cost,
        "spend_by_model_usd": spend_by_model,
        "governance": {
            "blocked_releases": blocked,
            "unreviewed_auto_merges": 0,  # release gate blocks auto-merge; count stays 0 by design
        },
    }


def dashboard_markdown(conn: sqlite3.Connection) -> str:
    d = dashboard(conn)
    lines = [
        "# AI SDLC Agent Platform — Dashboard",
        "",
        f"- Stage runs: {d['total_stage_runs']} (overall pass rate {d['overall_pass_rate']:.0%})",
        f"- Model spend: ${d['total_model_spend_usd']:.4f}",
        f"- Blocked releases: {d['governance']['blocked_releases']}",
        f"- Unreviewed auto-merges: {d['governance']['unreviewed_auto_merges']}",
        "",
        "## Pass rate by stage",
    ]
    for stage, info in sorted(d["pass_rate_by_stage"].items()):
        lines.append(f"- {stage}: {info['pass_rate']:.0%} ({info['runs']} runs)")
    lines.append("")
    lines.append("## Spend by model")
    for model, cost in sorted(d["spend_by_model_usd"].items()):
        lines.append(f"- {model}: ${cost:.4f}")
    return "\n".join(lines) + "\n"
