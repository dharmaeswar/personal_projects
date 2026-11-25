"""End-to-end demo: run the analytics agent over the eval task set.

Writes eval_report.json, eval_report.txt and baseline.json next to this
file, and prints the report. Run from the project root:

    python run_demo.py
    python -m pytest -q
"""

from __future__ import annotations

import json
import os

from agent_eval.agent import AnalyticsAgent
from agent_eval.data_quality import run_quality_sweep
from agent_eval.evals import run_eval_set
from agent_eval.experiments import analyze_experiment
from agent_eval.provenance import render_report
from agent_eval.regression import (load_baseline, release_gate,
                                   save_baseline)
from agent_eval.sandbox import Sandbox
from agent_eval.tools import ToolServer

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    sandbox = Sandbox(role="analyst")
    agent = AnalyticsAgent(ToolServer(sandbox))
    results = run_eval_set(agent, sandbox)
    baseline = load_baseline(os.path.join(HERE, "baseline.json"))
    gate = release_gate(results, baseline)
    report = render_report(results, gate)
    print(report)

    # Data quality agent over the seeded warehouse snapshot.
    rows = [dict(zip(("id", "community", "title", "score", "comments",
                      "created_day"), row))
            for row in sandbox.conn.execute(
                "SELECT * FROM posts").fetchall()]
    sweep = run_quality_sweep({
        "table": "posts", "today_day": 29, "last_load_day": 29,
        "sla_days": 1, "row_count": len(rows), "expected_rows": len(rows),
        "columns": ["id", "community", "title", "score", "comments",
                    "created_day"],
        "expected_columns": ["id", "community", "title", "score",
                             "comments", "created_day"],
        "rows": rows, "key": "id", "null_columns": ["score", "comments"],
    })
    print(f"\nData quality sweep: {sweep['summary']}")

    # AI-powered experiment analysis on a seeded A/B test.
    experiment = analyze_experiment(
        10000, 1000, 10000, 1150,
        guardrails=[{"name": "retention", "control_rate": 0.80,
                     "treatment_rate": 0.79, "max_relative_drop": 0.05}])
    print(f"Experiment analysis: {experiment['recommendation']} — "
          f"p={experiment['p_value']}, uplift"
          f" {experiment['relative_uplift']:.1%}; "
          + "; ".join(experiment["reasons"]))

    with open(os.path.join(HERE, "eval_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    with open(os.path.join(HERE, "eval_report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(report)
    save_baseline(results, os.path.join(HERE, "baseline.json"))
    print(f"Release gate: {gate['gate']}")
    print(f"Audit entries recorded: {len(sandbox.audit)}")
    return 0 if gate["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
