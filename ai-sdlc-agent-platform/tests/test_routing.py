import pytest

from sdlc_agents.routing import Model, ModelRouter

MODELS = [
    Model("small", capability=0.55, cost_per_1k_tokens=0.15, latency_ms_per_1k_tokens=120),
    Model("standard", capability=0.75, cost_per_1k_tokens=0.60, latency_ms_per_1k_tokens=250),
    Model("strong", capability=0.92, cost_per_1k_tokens=2.40, latency_ms_per_1k_tokens=600),
]


def test_codegen_routes_to_strongest_cheapest_qualifying():
    router = ModelRouter(MODELS)
    decision = router.route("codegen", tokens=1000)
    assert decision.model.name == "strong"
    assert decision.estimated_cost == 2.40


def test_triage_routes_to_cheapest():
    router = ModelRouter(MODELS)
    assert router.route("triage", tokens=1000).model.name == "small"


def test_review_routes_to_standard():
    router = ModelRouter(MODELS)
    assert router.route("review", tokens=1000).model.name == "standard"


def test_latency_budget_filters_out_slow_models():
    router = ModelRouter(MODELS)
    with pytest.raises(ValueError, match="latency budget"):
        router.route("codegen", tokens=1000, max_latency_ms=100)


def test_no_model_meets_capability_floor():
    router = ModelRouter([Model("tiny", 0.10, 0.01, 10)])
    with pytest.raises(ValueError, match="capability floor"):
        router.route("codegen", tokens=100)


def test_unknown_task_type_rejected():
    with pytest.raises(ValueError, match="unknown task type"):
        ModelRouter(MODELS).route("deploy", tokens=100)


def test_ledger_tracks_spend_by_model():
    router = ModelRouter(MODELS)
    router.route("triage", tokens=1000)
    router.route("codegen", tokens=1000)
    assert router.ledger.total_cost() == 2.55
    assert router.ledger.cost_by_model() == {"small": 0.15, "strong": 2.40}
