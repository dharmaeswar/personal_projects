"""Agentic evaluation harness: LLM-judge scoring of agent trajectories.

This is the Nova Evals layer for the project: instead of validating the
*claims* of an analytics agent (what ``agents.py`` / ``pipeline.py`` do),
it validates the *behaviour* of an agent that uses tools over several
turns — the way an agentic product such as Iterable Nova has to be
evaluated before it ships.

What it covers, all standard library and deterministic:

* ``judge_trajectory`` — a rubric judge that scores one multi-turn
  trajectory on four criteria: grounding (answer claims backed by tool
  results), tool use (valid tools, required args, a result for every
  call), coherence (numbers in the answer match the evidence), and
  reasoning (reasoning steps cite the evidence they use).
* ``generate_synthetic_cases`` — a seeded synthetic-data pipeline that
  builds eval cases: clean trajectories plus known-bad mutations
  (hallucinated claim, unknown tool, missing tool result, unsupported
  answer), each with an expected verdict.
* ``run_benchmark`` — runs the judge over a case set: pass rate, judge
  accuracy against expected verdicts, per-criterion means.
* ``detect_regression`` — compares the current run against a baseline
  run with a Welch t-test and a bootstrap CI on the score difference,
  so a drop is only called a regression when it is real, not noise.
* ``diagnose_failures`` — maps each failure to the fix it needs:
  prompt, tool, context, rubric, or harness.
"""

import random
import re

from . import stats

# Tools the demo agent may call: name -> required argument names.
TOOLS = {
    "search_docs": ["query"],
    "run_query": ["sql"],
    "compute": ["expression"],
}

_PASS_OVERALL = 0.70
_PASS_MIN_CRITERION = 0.50

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "it", "its", "this", "that", "by", "from",
    "as", "at", "be", "has", "have", "had", "will", "would", "can", "per",
}

_WORD_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _tokens(text):
    return _WORD_RE.findall((text or "").lower())


def _content_tokens(text):
    return [t for t in _tokens(text) if len(t) >= 4 and t not in _STOPWORDS]


def _evidence_text(trajectory):
    """All tool-result text, joined, for grounding checks."""
    return " ".join(
        s.get("result", "") for s in trajectory if s.get("kind") == "tool_result"
    )


def _tool_calls(trajectory):
    return [s for s in trajectory if s.get("kind") == "tool_call"]


def _answer_text(trajectory):
    parts = [s.get("text", "") for s in trajectory if s.get("kind") == "answer"]
    return " ".join(parts)


def _score_tool_use(trajectory):
    calls = _tool_calls(trajectory)
    if not calls:
        return 0.0, "no tool calls in trajectory"
    results = [s for s in trajectory if s.get("kind") == "tool_result"]
    valid = 0
    for i, call in enumerate(calls):
        tool = call.get("tool", "")
        args = call.get("args", {}) or {}
        if tool not in TOOLS:
            continue
        if any(req not in args for req in TOOLS[tool]):
            continue
        # A result must follow this call (same tool, later step).
        call_idx = trajectory.index(call)
        followed = any(
            trajectory.index(r) > call_idx and r.get("tool", "") == tool
            for r in results
        )
        if followed:
            valid += 1
    return valid / len(calls), f"{valid}/{len(calls)} tool calls valid"


def _score_grounding(trajectory):
    answer = _answer_text(trajectory)
    if not answer.strip():
        return 0.0, "no answer to ground"
    evidence = _evidence_text(trajectory)
    evidence_tokens = set(_tokens(evidence))
    sentences = [s.strip() for s in re.split(r"[.!?]\s*", answer) if s.strip()]
    supported = 0
    for sentence in sentences:
        tokens = set(_content_tokens(sentence))
        if tokens & evidence_tokens:
            supported += 1
    return supported / len(sentences), f"{supported}/{len(sentences)} claims grounded"


def _score_coherence(trajectory):
    answer = _answer_text(trajectory)
    numbers = _NUMBER_RE.findall(answer)
    if not numbers:
        return 1.0, "no numbers in answer"
    evidence = _evidence_text(trajectory)
    matched = sum(1 for n in numbers if n in evidence)
    return matched / len(numbers), f"{matched}/{len(numbers)} numbers match evidence"


def _score_reasoning(trajectory):
    steps = [s for s in trajectory if s.get("kind") == "reasoning"]
    if not steps:
        return 0.0, "no reasoning steps"
    evidence_tokens = set(_content_tokens(_evidence_text(trajectory)))
    tool_names = set(TOOLS)
    citing = 0
    for step in steps:
        tokens = set(_content_tokens(step.get("text", "")))
        if (tokens & evidence_tokens) or (tokens & tool_names):
            citing += 1
    return citing / len(steps), f"{citing}/{len(steps)} reasoning steps cite evidence"


def judge_trajectory(trajectory, tools=None):
    """Score one agent trajectory on the four rubric criteria.

    Returns a dict with per-criterion scores (0..1), the overall mean,
    a PASS/FAIL verdict, and a short note per criterion. A trajectory
    passes only when the overall score is at least 0.70 and neither
    grounding nor tool use falls below 0.50 — an agent that hallucinates
    or misuses tools must not pass on fluent reasoning alone. Two
    failures are hard fails whatever the mean says: an invented number
    in the answer (a hallucination) and any invalid tool call (unknown
    tool, missing required args, or a call with no result).
    """
    tools = tools or TOOLS
    scores = {}
    notes = {}
    for name, fn in (
        ("grounding", _score_grounding),
        ("tool_use", _score_tool_use),
        ("coherence", _score_coherence),
        ("reasoning", _score_reasoning),
    ):
        score, note = fn(trajectory)
        scores[name] = round(score, 4)
        notes[name] = note
    overall = round(sum(scores.values()) / len(scores), 4)
    hard_fails = []
    if scores["coherence"] < 1.0:
        hard_fails.append("hallucinated number in answer")
    if scores["tool_use"] < 1.0:
        hard_fails.append("invalid or unanswered tool call")
    verdict = (
        "PASS"
        if overall >= _PASS_OVERALL
        and scores["grounding"] >= _PASS_MIN_CRITERION
        and scores["tool_use"] >= _PASS_MIN_CRITERION
        and not hard_fails
        else "FAIL"
    )
    return {
        "scores": scores,
        "notes": notes,
        "overall": overall,
        "verdict": verdict,
        "hard_fails": hard_fails,
    }


# --- synthetic eval cases ---------------------------------------------------

_GOOD_RESULT_DOCS = (
    "Docs: churn playbook says offer a 20 percent discount to at-risk "
    "accounts and log the outreach in the CRM."
)
_GOOD_RESULT_QUERY = (
    "Query result: 42 at-risk accounts, average tenure 18 months, "
    "total monthly value 12500 dollars."
)


def _good_trajectory():
    return [
        {"kind": "reasoning",
         "text": "I need the churn playbook first, so I will call search_docs."},
        {"kind": "tool_call", "tool": "search_docs",
         "args": {"query": "churn playbook at-risk accounts"}},
        {"kind": "tool_result", "tool": "search_docs",
         "result": _GOOD_RESULT_DOCS},
        {"kind": "reasoning",
         "text": "The docs say offer a 20 percent discount; now I need the "
                 "at-risk accounts from run_query."},
        {"kind": "tool_call", "tool": "run_query",
         "args": {"sql": "SELECT * FROM accounts WHERE at_risk = true"}},
        {"kind": "tool_result", "tool": "run_query",
         "result": _GOOD_RESULT_QUERY},
        {"kind": "answer",
         "text": "There are 42 at-risk accounts with average tenure 18 months. "
                 "Offer a 20 percent discount to at-risk accounts and log the "
                 "outreach in the CRM. Total monthly value is 12500 dollars."},
    ]


def _mutate(trajectory, kind):
    """Return a known-bad copy of a good trajectory."""
    import copy

    traj = copy.deepcopy(trajectory)
    if kind == "hallucinated-claim":
        # Answer invents a number (99) that no tool result contains.
        traj[-1]["text"] += " Also, 99 accounts churned yesterday."
    elif kind == "bad-tool":
        traj[1]["tool"] = "delete_everything"
        traj[1]["args"] = {"target": "all"}
    elif kind == "missing-result":
        # The query runs but its result never comes back.
        traj = [s for s in traj if not (
            s.get("kind") == "tool_result" and s.get("tool") == "run_query")]
    elif kind == "unsupported-answer":
        traj[-1]["text"] = (
            "Switch every customer to the premium plan tomorrow and "
            "double prices without warning.")
    return traj


_CASE_KINDS = [
    ("good", "PASS"),
    ("hallucinated-claim", "FAIL"),
    ("bad-tool", "FAIL"),
    ("missing-result", "FAIL"),
    ("unsupported-answer", "FAIL"),
]


def generate_synthetic_cases(n=10, seed=11):
    """Seeded synthetic benchmark: clean cases plus known-bad mutations.

    The case mix cycles through the five kinds, so a run of 10 cases has
    2 good and 8 bad trajectories. ``seed`` only shuffles the order, so
    the same seed always gives the same benchmark.
    """
    rng = random.Random(seed)
    cases = []
    for i in range(n):
        kind, expected = _CASE_KINDS[i % len(_CASE_KINDS)]
        if kind == "good":
            traj = _good_trajectory()
        else:
            traj = _mutate(_good_trajectory(), kind)
        cases.append({
            "id": f"EVAL-{i + 1:02d}",
            "kind": kind,
            "expected": expected,
            "trajectory": traj,
        })
    rng.shuffle(cases)
    return cases


# --- benchmark, regression, diagnosis ---------------------------------------

def run_benchmark(cases, tools=None):
    """Judge every case; aggregate pass rate, accuracy, criterion means."""
    results = []
    for case in cases:
        judged = judge_trajectory(case["trajectory"], tools=tools)
        results.append({
            "id": case["id"],
            "kind": case["kind"],
            "expected": case["expected"],
            "verdict": judged["verdict"],
            "overall": judged["overall"],
            "scores": judged["scores"],
            "correct": judged["verdict"] == case["expected"],
        })
    n = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    correct = sum(1 for r in results if r["correct"])
    means = {
        name: round(sum(r["scores"][name] for r in results) / n, 4)
        for name in ("grounding", "tool_use", "coherence", "reasoning")
    } if n else {}
    return {
        "n": n,
        "pass_rate": round(passed / n, 4) if n else 0.0,
        "judge_accuracy": round(correct / n, 4) if n else 0.0,
        "mean_overall": round(
            sum(r["overall"] for r in results) / n, 4) if n else 0.0,
        "criterion_means": means,
        "results": results,
    }


def detect_regression(current_scores, baseline_scores, min_drop=0.05):
    """Is the current run really worse than the baseline run?

    A regression needs both: the mean score dropped by at least
    ``min_drop`` AND the drop is statistically real — the Welch t-test
    p-value is below 0.05 and the bootstrap 95% CI on the mean
    difference excludes zero. A small wobble on few cases is noise.
    """
    current = list(current_scores)
    baseline = list(baseline_scores)
    if not current or not baseline:
        return {"regression": False, "reason": "empty score list"}
    mean_diff = stats.mean(current) - stats.mean(baseline)
    test = stats.welch_t_test(current, baseline)
    lo, hi = stats.bootstrap_ci_mean_diff(current, baseline)
    regression = (
        mean_diff <= -min_drop and test["p"] < 0.05 and hi < 0
    )
    return {
        "regression": regression,
        "mean_diff": round(mean_diff, 4),
        "current_mean": round(stats.mean(current), 4),
        "baseline_mean": round(stats.mean(baseline), 4),
        "p_value": round(test["p"], 4),
        "ci_95": (round(lo, 4), round(hi, 4)),
    }


_FIX_MAP = {
    "tool_use": ("tool", "Fix the tool schema or the agent's tool calls."),
    "grounding": ("prompt", "Tighten the prompt: answer only from tool results."),
    "coherence": ("context", "Fix retrieval/context: the answer used numbers not in evidence."),
    "reasoning": ("prompt", "Tighten the prompt: reason from the evidence step by step."),
}


def diagnose_failures(benchmark):
    """Map each failed case to the fix it needs.

    A case the judge failed even though it should pass points at the
    rubric itself; otherwise the lowest-scoring criterion names the fix.
    """
    diagnoses = []
    for r in benchmark["results"]:
        if r["verdict"] == "PASS":
            continue
        if r["expected"] == "PASS":
            diagnoses.append({
                "id": r["id"], "kind": r["kind"], "category": "rubric",
                "detail": "Judge failed a good trajectory; recalibrate the rubric.",
            })
            continue
        worst = min(r["scores"], key=lambda k: r["scores"][k])
        category, detail = _FIX_MAP[worst]
        diagnoses.append({
            "id": r["id"], "kind": r["kind"], "category": category,
            "detail": detail,
        })
    return diagnoses


def render_evals_report(benchmark, regression=None, diagnoses=None):
    lines = [
        "AGENTIC EVALS REPORT",
        f"Cases judged: {benchmark['n']}",
        f"Pass rate: {benchmark['pass_rate']:.0%} "
        f"({sum(1 for r in benchmark['results'] if r['verdict'] == 'PASS')}"
        f"/{benchmark['n']})",
        f"Judge accuracy vs expected verdicts: {benchmark['judge_accuracy']:.0%}",
        f"Mean overall score: {benchmark['mean_overall']:.3f}",
        "Criterion means: " + ", ".join(
            f"{k} {v:.3f}" for k, v in benchmark["criterion_means"].items()),
        "",
        "Per-case results:",
    ]
    for r in benchmark["results"]:
        lines.append(
            f"  {r['id']} [{r['kind']}] expected {r['expected']}, "
            f"judged {r['verdict']} (overall {r['overall']:.2f}) "
            f"{'OK' if r['correct'] else 'JUDGE MISS'}")
    if regression is not None:
        lines += [
            "",
            "Regression check vs baseline run:",
            f"  current mean {regression['current_mean']:.3f}, "
            f"baseline mean {regression['baseline_mean']:.3f}, "
            f"diff {regression['mean_diff']:+.3f}",
            f"  Welch p={regression['p_value']}, 95% CI "
            f"{regression['ci_95']}",
            "  REGRESSION DETECTED" if regression["regression"]
            else "  No regression: change is within noise.",
        ]
    if diagnoses:
        lines += ["", "Failure diagnoses (failure -> fix):"]
        for d in diagnoses:
            lines.append(f"  {d['id']} [{d['kind']}] -> {d['category']}: {d['detail']}")
    return "\n".join(lines) + "\n"
