from pathlib import Path

from sdlc_agents.pipeline import run_pipeline

BASE = Path(__file__).resolve().parent.parent


def test_full_pipeline(tmp_path):
    report = run_pipeline(BASE / "data" / "seed_repo.json", tmp_path / "run.sqlite")
    assert set(report["tickets"]) == {"SDLC-101", "SDLC-102", "SDLC-103"}
    for ticket_id, stages in report["tickets"].items():
        assert all(s["passed"] for s in stages.values()), ticket_id
    assert report["grounding_first_try_hit_rate"] == 1.0
    assert report["tool_totals"]["calls"] == 9  # 3 tickets x (read_file + open_pr + run_tests)
    assert report["tool_totals"]["failed_calls"] == 0
    assert report["model_spend_usd"] > 0
    assert report["benchmark"]["improved_mean"] == 1.0
    assert report["benchmark"]["ab_vs_baseline"]["verdict"] == "candidate wins"
    assert report["pareto_frontier_cost_quality"] == [(0.02, 0.55), (0.10, 0.82), (0.35, 0.93)]
    assert report["dashboard"]["governance"]["blocked_releases"] == 0
