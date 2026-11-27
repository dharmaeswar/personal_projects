import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsi_agent import agent, data, evaluate  # noqa: E402


def test_run_study_releases_only_when_approved():
    slides = data.make_study(n_per_arm=3, seed=11)
    held = agent.run_study(slides, "q", approve=False)
    assert held["status"] == "held_for_human_review"
    released = agent.run_study(slides, "q", approve=True)
    assert released["status"] == "released"


def test_reviewer_rejects_ungrounded_claim():
    reviewer = agent.ReviewerAgent()
    result = reviewer.review(
        ["Mean tile score: treated 1.5 vs control 1.2.",
         "The drug cures everything, improvement 999%."],
        {1.5, 1.2})
    assert len(result["kept"]) == 1
    assert len(result["rejected"]) == 1


def test_run_study_trace_covers_all_agents():
    slides = data.make_study(n_per_arm=2, seed=12)
    result = agent.run_study(slides, "q", approve=True)
    agents = {t["agent"] for t in result["trace"]}
    assert {"planner", "preprocessor", "analyst", "reviewer"} <= agents
    assert len(result["kept_claims"]) == 4
    assert result["rejected_claims"] == []


def test_evaluate_all_checks_pass():
    result = evaluate.evaluate()
    assert result["passed"] is True
    assert result["checks"]["reproducible_same_seed"] is True
