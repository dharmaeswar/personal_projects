"""Evaluation harness: trajectory-level evals with regression comparison.

Each seeded task states what a good research run must do: which documents
it must cite, which figures it must state, and which tools it must use.
A run is scored on groundedness (validator passed), citation coverage,
tool-use accuracy, and reproducibility (same answer text on a repeat run).
The harness runs the same tasks under a baseline config (no validator,
single pass) and an improved config, and reports the delta plus a release
gate: the improved config must not regress groundedness or citation
coverage.
"""

import hashlib

from .orchestrator import ResearchRun

# Seeded eval tasks. Expected figures are the synthetic ground-truth values
# from the seeded dataset documents.
EVAL_TASKS = [
    {
        "id": "EV-MOM-01",
        "question": "What is the momentum signal and what did the momentum factor return?",
        "must_cite": ["RN-MOM-01", "DATA-MOM-01"],
        "expected_figures": [("momentum annualised return", 6.2),
                             ("momentum sharpe", 0.54)],
        "expected_tools": ["search_knowledge", "read_code", "compute_statistic"],
    },
    {
        "id": "EV-CARRY-01",
        "question": "How does FX carry work and what is its Sharpe ratio?",
        "must_cite": ["RN-CARRY-01", "DATA-CARRY-01"],
        "expected_figures": [("carry annualised return", 4.8),
                             ("carry sharpe", 0.53)],
        "expected_tools": ["search_knowledge", "compute_statistic"],
    },
    {
        "id": "EV-VOL-01",
        "question": "How does volatility targeting keep the portfolio at its target?",
        "must_cite": ["RN-VOL-01", "DATA-VOL-01"],
        "expected_figures": [("volatility target", 10.0),
                             ("realised volatility", 10.3)],
        "expected_tools": ["search_knowledge"],
    },
    {
        "id": "EV-MREV-01",
        "question": "Why hold a mean-reversion sleeve despite its lower Sharpe ratio?",
        "must_cite": ["RN-MREV-01"],
        "expected_figures": [("mean reversion sharpe", 0.28)],
        "expected_tools": ["search_knowledge"],
    },
    {
        "id": "EV-CODE-01",
        "question": "Show me the momentum signal code and its lookback.",
        "must_cite": ["CODE-MOM-01"],
        "expected_figures": [],
        "expected_tools": ["search_knowledge", "read_code"],
    },
    {
        "id": "EV-ZSCORE-01",
        "question": "How is the z-score computed for mean reversion?",
        "must_cite": ["CODE-ZSCORE-01"],
        "expected_figures": [],
        "expected_tools": ["read_code"],
    },
]


def _answer_hash(answer_text):
    return hashlib.sha256(answer_text.encode("utf-8")).hexdigest()[:12]


def score_run(task, result, repeat_result):
    """Score one task run against its expectations."""
    answer = result["answer"]
    cited = set(answer["citations"])
    must_cite = set(task["must_cite"])
    citation_coverage = (
        len(cited & must_cite) / len(must_cite) if must_cite else 1.0
    )
    claimed = {c["label"]: c["value"] for c in answer["claims"]}
    figures_ok = all(
        label in claimed and abs(claimed[label] - value) <= 0.05
        for label, value in task["expected_figures"]
    )
    tools_used = set(result["tools_used"])
    tool_accuracy = (
        len(set(task["expected_tools"]) & tools_used) / len(task["expected_tools"])
        if task["expected_tools"] else 1.0
    )
    validation = result["validation"]
    grounded = bool(validation and validation["passed"])
    reproducible = (
        _answer_hash(result["answer"]["text"])
        == _answer_hash(repeat_result["answer"]["text"])
    )
    return {
        "task_id": task["id"],
        "grounded": grounded,
        "citation_coverage": round(citation_coverage, 2),
        "figures_correct": figures_ok,
        "tool_accuracy": round(tool_accuracy, 2),
        "reproducible": reproducible,
    }


def run_evaluation(use_validator=True):
    """Run all seeded tasks under one config; return per-task scores."""
    scored = []
    for task in EVAL_TASKS:
        result = ResearchRun(task["question"], use_validator=use_validator).run()
        repeat = ResearchRun(task["question"], use_validator=use_validator).run()
        scored.append(score_run(task, result, repeat))
    return scored


def summarize(scored):
    """Aggregate rates over per-task scores."""
    n = len(scored)
    if n == 0:
        return {}
    return {
        "tasks": n,
        "grounded_rate": round(sum(s["grounded"] for s in scored) / n, 2),
        "mean_citation_coverage": round(
            sum(s["citation_coverage"] for s in scored) / n, 2),
        "figures_correct_rate": round(
            sum(s["figures_correct"] for s in scored) / n, 2),
        "mean_tool_accuracy": round(
            sum(s["tool_accuracy"] for s in scored) / n, 2),
        "reproducible_rate": round(
            sum(s["reproducible"] for s in scored) / n, 2),
    }


def regression_report():
    """Baseline (no validator) vs improved (validator) comparison + gate."""
    baseline = run_evaluation(use_validator=False)
    improved = run_evaluation(use_validator=True)
    base = summarize(baseline)
    imp = summarize(improved)
    gate = (
        imp["grounded_rate"] >= base["grounded_rate"]
        and imp["mean_citation_coverage"] >= base["mean_citation_coverage"]
    )
    return {
        "baseline": {"config": "no validator, single pass", "summary": base,
                     "tasks": baseline},
        "improved": {"config": "validator + one repair pass", "summary": imp,
                     "tasks": improved},
        "delta_grounded_rate": round(imp["grounded_rate"] - base["grounded_rate"], 2),
        "delta_citation_coverage": round(
            imp["mean_citation_coverage"] - base["mean_citation_coverage"], 2),
        "release_gate_passed": gate,
    }
