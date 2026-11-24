"""Rubric-based LLM-as-judge for support cases.

The built-in judge is a deterministic, rule-based stand-in: it scores a
case transcript against the rubric by checking the agent's turns for the
required facts, forbidden claims, empathy markers, and resolution
markers. It is reproducible offline and has no model API calls. A
model-backed judge plugs into the same ``grade()`` interface — replace
``RuleBasedJudge`` with an LLM call that returns the same ``JudgeResult``
shape and the rest of the system (coaching, simulation, evaluation) is
unchanged.

Two prompt versions are supported so prompt changes can be A/B-tested:
``v1`` is the baseline rubric; ``v2`` is stricter on policy compliance
(a forbidden claim caps that criterion at 0 and blocks a pass).
"""

from dataclasses import dataclass, field

from .data import RUBRIC, PASS_OVERALL, PASS_MIN_CRITERION, SupportCase

EMPATHY_MARKERS = (
    "sorry", "understand", "i understand", "worry", "frustrat",
    "thank", "appreciate", "sorry for", "no problem",
)
RESOLUTION_MARKERS = (
    "i've cancelled", "i have cancelled", "i'll open", "i will open",
    "i can open", "released", "will be released", "escalated", "rebook",
    "i can help", "let you know", "keep you updated", "monitor",
    "i'll keep", "refund will arrive", "will arrive",
)
# Words that make an answer hard to read for a guest (clarity penalty).
JARGON = (
    "effectuated", "finalisation", "adjudication", "remittance",
    "disbursement cadence", "temporal parameters", "subsequent to",
)


@dataclass
class JudgeResult:
    case_id: str
    prompt_version: str
    scores: dict  # criterion key -> 0, 1, or 2
    overall: float  # weighted 0-2 score
    passed: bool
    evidence: dict = field(default_factory=dict)  # criterion key -> evidence string

    def weakest(self):
        """Criterion keys sorted worst-first (ties broken by rubric weight)."""
        weight = {c.key: c.weight for c in RUBRIC}
        return sorted(self.scores, key=lambda k: (self.scores[k], -weight[k]))


def _agent_text(case):
    return " ".join(t for speaker, t in case.transcript if speaker == "agent")


def _score_accuracy(case, text):
    lowered = text.lower()
    hits = [f for f in case.required_facts if f.lower() in lowered]
    if not case.required_facts:
        return 1, "no required facts defined for this case"
    if len(hits) == len(case.required_facts):
        return 2, f"states all required facts: {', '.join(hits)}"
    if hits:
        missing = [f for f in case.required_facts if f.lower() not in lowered]
        return 1, f"states {', '.join(hits)}; misses {', '.join(missing)}"
    return 0, "states none of the required facts"


def _score_empathy(case, text):
    lowered = text.lower()
    hits = [m for m in EMPATHY_MARKERS if m in lowered]
    if len(hits) >= 2:
        return 2, f"acknowledges impact ({', '.join(sorted(set(hits))[:2])})"
    if hits:
        return 1, f"one courtesy marker ({hits[0]}); no impact acknowledgement"
    return 0, "no empathy or courtesy marker in the agent turns"


def _score_policy(case, text, prompt_version):
    lowered = text.lower()
    bad = [c for c in case.forbidden_claims if c.lower() in lowered]
    if bad:
        if prompt_version == "v2":
            return 0, f"makes a forbidden claim: {', '.join(bad)} (v2: hard fail)"
        return 0, f"makes a forbidden claim: {', '.join(bad)}"
    if case.required_facts and _score_accuracy(case, text)[0] == 2:
        return 2, "follows the stated policy; no forbidden claim"
    return 1, "no forbidden claim, but the policy facts are incomplete"


def _score_resolution(case, text):
    lowered = text.lower()
    hits = [m for m in RESOLUTION_MARKERS if m in lowered]
    if hits:
        return 2, f"concrete next step given ({hits[0]})"
    return 0, "no concrete next step or resolved outcome"


def _score_clarity(case, text):
    lowered = text.lower()
    bad = [j for j in JARGON if j in lowered]
    words = len(text.split())
    if bad:
        return 0, f"jargon-heavy ({', '.join(bad)})"
    if words > 120:
        return 1, f"long answer ({words} words); could be shorter"
    return 2, "short, plain answer"


class RuleBasedJudge:
    """Deterministic stand-in for an LLM-as-judge grader."""

    def __init__(self, prompt_version="v1"):
        if prompt_version not in ("v1", "v2"):
            raise ValueError("prompt_version must be 'v1' or 'v2'")
        self.prompt_version = prompt_version

    def grade(self, case: SupportCase) -> JudgeResult:
        text = _agent_text(case)
        scores = {}
        evidence = {}
        scores["accuracy"], evidence["accuracy"] = _score_accuracy(case, text)
        scores["empathy"], evidence["empathy"] = _score_empathy(case, text)
        scores["policy_compliance"], evidence["policy_compliance"] = _score_policy(
            case, text, self.prompt_version)
        scores["resolution"], evidence["resolution"] = _score_resolution(case, text)
        scores["clarity"], evidence["clarity"] = _score_clarity(case, text)
        overall = sum(c.weight * scores[c.key] for c in RUBRIC)
        passed = (overall >= PASS_OVERALL
                  and min(scores.values()) >= PASS_MIN_CRITERION)
        return JudgeResult(case.case_id, self.prompt_version, scores,
                           round(overall, 3), passed, evidence)
