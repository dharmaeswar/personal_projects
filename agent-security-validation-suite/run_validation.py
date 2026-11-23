"""Run the agent security validation suites and write the reports."""
import json
import os

from agent_security.abac import run_abac_suite
from agent_security.evals import (run_guardrail_suite, run_mcp_suite,
                                  summarize)
from agent_security.monitor import SessionMonitor
from agent_security.report import render_json, render_text

HERE = os.path.dirname(os.path.abspath(__file__))


def demo_session_anomalies():
    """A scripted session that trips the monitor: burst + denied retry."""
    mon = SessionMonitor()
    t = 1000
    for i in range(6):  # 6 calls inside 60s -> burst
        mon.record(t + i * 5, "search_kb", True)
    mon.record(t + 40, "delete_record", False, "missing-scope:write:admin")
    mon.record(t + 45, "delete_record", False, "missing-scope:write:admin")
    mon.record(t + 50, "delete_record", False, "missing-scope:write:admin")
    mon.record(t + 55, "delete_record", True)  # succeeds after denials
    return mon.anomalies()


def main():
    guardrail_rows = run_guardrail_suite()
    summary = summarize(guardrail_rows)
    mcp_rows = run_mcp_suite()
    anomalies = demo_session_anomalies()
    abac_rows, abac_allowed, abac_denied = run_abac_suite()
    abac_passed = sum(1 for r in abac_rows if r["passed"])
    text = render_text(guardrail_rows, summary, mcp_rows, anomalies)
    text += "\nABAC / CARDS attribute-repository scenarios: %d/%d passed" % (
        abac_passed, len(abac_rows))
    text += " (%d allowed, %d denied)\n" % (abac_allowed, abac_denied)
    for r in abac_rows:
        if not r["passed"]:
            text += "  FAIL %s -> %s %s: %s\n" % (
                r["principal"], r["resource"], r["action"], r["rule"])
    print(text)
    with open(os.path.join(HERE, "validation_report.txt"), "w") as f:
        f.write(text)
    report = json.loads(render_json(guardrail_rows, summary, mcp_rows,
                                    anomalies))
    report["abac_rows"] = abac_rows
    with open(os.path.join(HERE, "validation_report.json"), "w") as f:
        f.write(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
