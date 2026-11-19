"""Run the agent security validation suites and write the reports."""
import os

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
    text = render_text(guardrail_rows, summary, mcp_rows, anomalies)
    print(text)
    with open(os.path.join(HERE, "validation_report.txt"), "w") as f:
        f.write(text)
    with open(os.path.join(HERE, "validation_report.json"), "w") as f:
        f.write(render_json(guardrail_rows, summary, mcp_rows, anomalies))


if __name__ == "__main__":
    main()
