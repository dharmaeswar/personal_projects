"""Offline + online evaluation: agreement with human labels, prompt A/B,
and a release gate.

The judge is measured, not assumed: every prompt version is run over the
human-labeled case set and compared on exact-match agreement and mean
absolute error per criterion. A release gate blocks a prompt version
whose agreement drops below the bar, so a worse grader cannot ship
silently.
"""

from dataclasses import dataclass, field

from .data import CASES, RUBRIC
from .judge import RuleBasedJudge


@dataclass
class OfflineReport:
    prompt_version: str
    n_cases: int
    agreement: float  # exact-match rate across all criterion scores
    mean_abs_error: float
    per_criterion_agreement: dict
    overall_agreement: float  # share of cases where pass/fail matches humans
    gate_passed: bool = False


def _human_overall(case):
    overall = sum(c.weight * case.human_labels[c.key] for c in RUBRIC)
    return round(overall, 3)


def evaluate_offline(judge, cases=None, min_agreement=0.75, max_mae=0.5):
    cases = list(cases if cases is not None else CASES)
    if not cases:
        raise ValueError("no cases to evaluate")
    total = 0
    matches = 0
    abs_error = 0.0
    per_criterion = {c.key: [0, 0] for c in RUBRIC}  # key -> [matches, total]
    pass_matches = 0
    for case in cases:
        result = judge.grade(case)
        human_pass = _human_overall(case) >= 1.4 and min(
            case.human_labels.values()) >= 1
        if result.passed == human_pass:
            pass_matches += 1
        for criterion in RUBRIC:
            total += 1
            per_criterion[criterion.key][1] += 1
            diff = abs(result.scores[criterion.key]
                       - case.human_labels[criterion.key])
            abs_error += diff
            if diff == 0:
                matches += 1
                per_criterion[criterion.key][0] += 1
    agreement = round(matches / total, 3)
    mae = round(abs_error / total, 3)
    report = OfflineReport(
        prompt_version=judge.prompt_version,
        n_cases=len(cases),
        agreement=agreement,
        mean_abs_error=mae,
        per_criterion_agreement={
            k: round(m / t, 3) for k, (m, t) in per_criterion.items()},
        overall_agreement=round(pass_matches / len(cases), 3),
    )
    report.gate_passed = agreement >= min_agreement and mae <= max_mae
    return report


def compare_prompts(cases=None, versions=("v1", "v2")):
    """Head-to-head A/B of prompt versions on the same labeled set."""
    rows = []
    for version in versions:
        rows.append(evaluate_offline(RuleBasedJudge(version), cases))
    rows.sort(key=lambda r: (-r.agreement, r.mean_abs_error))
    return rows
