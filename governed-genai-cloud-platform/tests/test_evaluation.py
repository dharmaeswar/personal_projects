from genai_platform.evaluation import Observability, run_evaluation
from genai_platform.rag import demo_knowledge_base


def test_evaluation_passes_all_seeded_cases():
    report = run_evaluation(demo_knowledge_base())
    assert report["total"] == 8
    assert report["passed"] == 8
    assert report["pass_rate"] == 1.0
    assert report["failures"] == []


def test_evaluation_reports_by_category():
    report = run_evaluation(demo_knowledge_base())
    assert report["by_category"]["accuracy"]["total"] == 6
    assert report["by_category"]["safety"]["total"] == 2


def test_observability_empty_summary():
    assert Observability().summary() == {"calls": 0}


def test_observability_aggregates_cost_by_team_and_model():
    obs = Observability(
        [
            {
                "team": "credit",
                "use_case": "qa",
                "model_id": "m-a",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.001,
                "latency_ms_p50": 400,
            },
            {
                "team": "credit",
                "use_case": "qa",
                "model_id": "m-b",
                "input_tokens": 20,
                "output_tokens": 10,
                "cost_usd": 0.004,
                "latency_ms_p50": 900,
            },
            {
                "team": "treasury",
                "use_case": "wires",
                "model_id": "m-a",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.001,
                "latency_ms_p50": 400,
            },
        ]
    )
    summary = obs.summary()
    assert summary["calls"] == 3
    assert summary["total_tokens"] == 60
    assert summary["total_cost_usd"] == 0.006
    assert summary["cost_by_team"] == {"credit": 0.005, "treasury": 0.001}
    assert summary["cost_by_model"]["m-b"] == 0.004


def test_recommend_model_picks_cheapest_passing_model():
    obs = Observability(
        [
            {
                "team": "credit",
                "use_case": "qa",
                "model_id": "m-cheap",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.001,
                "latency_ms_p50": 400,
            },
            {
                "team": "credit",
                "use_case": "qa",
                "model_id": "m-pricey",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.009,
                "latency_ms_p50": 900,
            },
        ]
    )
    assert obs.recommend_model({"m-cheap": 1.0, "m-pricey": 1.0}) == "m-cheap"
    assert obs.recommend_model({"m-cheap": 0.5, "m-pricey": 1.0}) == "m-pricey"
    assert obs.recommend_model({"m-cheap": 0.5, "m-pricey": 0.5}) is None
