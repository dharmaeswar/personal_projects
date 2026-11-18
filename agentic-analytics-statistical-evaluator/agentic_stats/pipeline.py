"""Pipeline: plan -> analyse -> validate -> report."""

from .agents import AnalystAgent, PlannerAgent, ValidatorAgent
from .data import build_dataset


def run_pipeline(question="Does the treatment improve outcomes?", n_per_arm=120):
    rows = build_dataset(n_per_arm=n_per_arm)
    plan = PlannerAgent().plan(question)
    claims = AnalystAgent().analyse(rows)
    results = ValidatorAgent().validate(rows, claims)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    report = {
        "question": question,
        "n_rows": len(rows),
        "plan_steps": len(plan["steps"]),
        "claims": claims,
        "validation": results,
        "passed": passed,
        "failed": len(results) - passed,
    }
    return report


def render_report(report):
    lines = [
        "Agentic Analytics — Statistical Validation Report",
        f"Question: {report['question']}",
        f"Rows: {report['n_rows']}  |  Plan steps: {report['plan_steps']}",
        f"Claims validated: {report['passed']} passed, {report['failed']} failed",
        "",
    ]
    for v in report["validation"]:
        lines.append(f"{v['id']} [{v['verdict']}] {v['text']}")
        lines.append(f"    raw p = {v['raw_p']:.4g}, Bonferroni pass = {v['bonferroni_pass']}")
        if "ci_95" in v:
            lines.append(
                f"    95% bootstrap CI for mean difference: {v['ci_95']}, "
                f"Cohen's d = {v['cohens_d']}, power = {v['power']}")
        if "interaction_p" in v:
            lines.append(
                f"    interaction effect = {v['interaction']}, "
                f"interaction p = {v['interaction_p']}")
        if "responder_rate_treatment" in v:
            lines.append(
                f"    responder rate: treatment {v['responder_rate_treatment']}, "
                f"control {v['responder_rate_control']}")
        if "reason" in v:
            lines.append(f"    reason: {v['reason']}")
    return "\n".join(lines) + "\n"
