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
from agent_eval.evals import run_eval_set
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
