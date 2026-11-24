"""AI coaching: turn quality evidence into a coaching plan.

A plan targets the weakest criteria first. Each drill names the gap in
plain words, a concrete exercise, the target score, a linked help-center
article, and a simulation scenario the agent can practise on. Strengths
are named too, so the plan is not only a list of failures.
"""

from dataclasses import dataclass, field

from .data import KB_ARTICLES, RUBRIC, SIMULATION_SCENARIOS

# Drill library: criterion key -> (drill title, exercise, KB article, scenario)
DRILLS = {
    "accuracy": (
        "State the policy facts before the answer",
        "Before replying, list the two policy facts the case turns on and "
        "check each one against the help-center article. Quote the fact, "
        "not a paraphrase.",
        "kb-cancel-48h", "sim-cancel-late",
    ),
    "empathy": (
        "Name the impact, then solve",
        "Open with one sentence that names what the guest is feeling or "
        "losing (time, money, safety), then move to the fix. Never open "
        "with the policy.",
        "kb-safety", "sim-unsafe-stay",
    ),
    "policy_compliance": (
        "Say what the policy allows, not what it forbids",
        "Rewrite the last three replies that promised something outside "
        "policy. For each, write the sentence the policy actually allows.",
        "kb-extenuating", "sim-cancel-late",
    ),
    "resolution": (
        "End every reply with a next step",
        "Every reply must end with one concrete next step and who does it. "
        "If the case cannot close yet, say what happens next and when.",
        "kb-resolution-center", "sim-payout-hold",
    ),
    "clarity": (
        "Plain words, short sentences",
        "Rewrite the reply in under 60 words with no internal jargon. "
        "Read it aloud: if a guest would need to ask what a word means, "
        "replace the word.",
        "kb-refund-timeline", "sim-payout-hold",
    ),
}


@dataclass
class CoachingPlan:
    case_id: str
    overall: float
    strengths: list  # criterion labels scored 2
    drills: list  # list of dicts
    summary: str = ""


def build_coaching_plan(result, case_id=None):
    """Build a coaching plan from a JudgeResult."""
    labels = {c.key: c.label for c in RUBRIC}
    strengths = [labels[k] for k, v in result.scores.items() if v == 2]
    drills = []
    for key in result.weakest():
        if result.scores[key] == 2:
            continue
        title, exercise, article_id, scenario_id = DRILLS[key]
        article = next(a for a in KB_ARTICLES if a.article_id == article_id)
        scenario = next(s for s in SIMULATION_SCENARIOS
                        if s.scenario_id == scenario_id)
        drills.append({
            "criterion": labels[key],
            "score": result.scores[key],
            "evidence": result.evidence.get(key, ""),
            "drill": title,
            "exercise": exercise,
            "target_score": 2,
            "kb_article": f"{article.article_id}: {article.title}",
            "practice_scenario": f"{scenario.scenario_id}: {scenario.title}",
        })
    worst = result.weakest()[0] if result.scores else ""
    summary = (
        f"Case {result.case_id} scored {result.overall:.2f}/2.00 "
        f"({'pass' if result.passed else 'needs coaching'}). "
        f"Weakest area: {labels.get(worst, 'none')}."
    )
    return CoachingPlan(case_id or result.case_id, result.overall,
                        strengths, drills, summary)
