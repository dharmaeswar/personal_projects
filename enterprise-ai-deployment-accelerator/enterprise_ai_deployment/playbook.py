"""Reusable deployment playbook: turn one run's evidence into guidance.

The playbook is the artifact that makes a deployment reusable: the next
customer with the same pattern starts from this document instead of
from scratch. It records the use case, the eval evidence, the readiness
verdict, the rollout steps and the open risks.
"""


def generate_playbook(use_case, summary, report, ranked_cases=None) -> str:
    """Render a Markdown deployment playbook from a run's results."""
    lines = [
        f"# Deployment Playbook: {use_case.name}",
        "",
        f"Domain: {use_case.domain}",
        f"Use case: {use_case.description}",
        "",
        "## Evaluation evidence",
        "",
        f"- Eval cases run: {summary.total}",
        f"- Passed: {summary.passed} (pass rate {summary.pass_rate:.0%})",
        f"- Mean correctness: {summary.mean_correctness:.2f}",
        f"- Mean grounding: {summary.mean_grounding:.2f}",
        f"- p95 latency: {summary.p95_latency_ms} ms",
        f"- Total cost: ${summary.total_cost_usd:.4f}",
        f"- PII leaks: {summary.pii_leaks}",
        "",
        "## Readiness verdict",
        "",
        f"**{'READY FOR PRODUCTION' if report.passed else 'NOT READY — see failing checks'}**",
        "",
    ]
    for check in report.checks:
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- [{mark}] {check['name']}: {check['detail']}")
    lines += [
        "",
        "## Rollout steps",
        "",
        "1. Pilot with one customer team and a human in the loop on every "
        "escalated question.",
        "2. Watch the JSONL eval log daily: pass rate, grounding, latency, "
        "cost and PII leaks.",
        "3. Expand to more teams only after two consecutive passing eval "
        "runs with no PII leaks.",
        "4. Re-run the eval suite on every prompt, tool or document change; "
        "a failing gate blocks the release.",
        "",
        "## Risks and open items",
        "",
        "- The agent answers only from retrieved documents; questions with "
        "no grounding document escalate to a human.",
        "- Graders are deterministic rule-based stubs: swap in model-backed "
        "graders and human review before high-stakes decisions.",
        "- Cost figures are estimates from a token heuristic, not a bill.",
        "",
    ]
    if ranked_cases:
        lines += ["## Use-case ranking (this deployment)", ""]
        for entry in ranked_cases:
            case = entry["use_case"]
            lines.append(
                f"- {case.name}: score {entry['score']:.2f} "
                f"({entry['tier']})")
        lines.append("")
    return "\n".join(lines)
