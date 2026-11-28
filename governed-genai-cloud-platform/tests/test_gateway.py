import pytest

from genai_platform.gateway import (
    MODEL_CATALOG,
    Gateway,
    ModelBackend,
    PromptTemplate,
)


def _gateway():
    gateway = Gateway()
    gateway.register(ModelBackend("amazon.titan-text-premier-v1:0"))
    gateway.register(ModelBackend("anthropic.claude-3-5-sonnet-20241022-v2:0"))
    return gateway


def test_unknown_model_rejected():
    gateway = Gateway()
    with pytest.raises(ValueError, match="unknown model"):
        gateway.register(ModelBackend("openai.gpt-5"))


def test_routing_prefers_healthy_preferred_model():
    gateway = _gateway()
    chosen = gateway.route("amazon.titan-text-premier-v1:0")
    assert chosen.model_id == "amazon.titan-text-premier-v1:0"


def test_routing_fails_over_from_unhealthy_preferred():
    gateway = _gateway()
    gateway.backends[0].healthy = False
    chosen = gateway.route("amazon.titan-text-premier-v1:0")
    assert chosen.model_id == "anthropic.claude-3-5-sonnet-20241022-v2:0"


def test_routing_fails_when_nothing_healthy():
    gateway = _gateway()
    for backend in gateway.backends:
        backend.healthy = False
    with pytest.raises(RuntimeError, match="no healthy model backend"):
        gateway.route()


def test_guardrail_redacts_ssn_and_account():
    cleaned, actions = Gateway.apply_guardrails(
        "Borrower SSN 123-45-6789 account 123456789012 owes payment."
    )
    assert "123-45-6789" not in cleaned
    assert "123456789012" not in cleaned
    assert "redacted SSN" in actions
    assert "redacted account number" in actions


def test_guardrail_blocks_disallowed_topic():
    with pytest.raises(ValueError, match="blocked topic"):
        Gateway.apply_guardrails("Give me insider trading tips for tomorrow.")


def test_invoke_meters_cost_and_tokens():
    gateway = _gateway()
    result = gateway.invoke(
        "What is the covenant limit?",
        team="credit",
        use_case="covenant-qa",
        preferred_model="amazon.titan-text-premier-v1:0",
    )
    record = result["record"]
    assert record["model_id"] == "amazon.titan-text-premier-v1:0"
    assert record["input_tokens"] >= 1
    assert record["output_tokens"] >= 1
    assert record["cost_usd"] > 0
    assert len(gateway.usage) == 1


def test_prompt_template_render_and_missing_variable():
    template = PromptTemplate("qa", 1, "Answer from policy only: {question}")
    assert template.render(question="What is the limit?").startswith(
        "Answer from policy only:"
    )
    with pytest.raises(ValueError, match="missing prompt variable"):
        template.render()


def test_cost_by_team_aggregates():
    gateway = _gateway()
    gateway.invoke("q1", team="credit", use_case="qa")
    gateway.invoke("q2", team="credit", use_case="qa")
    gateway.invoke("q3", team="treasury", use_case="qa")
    totals = gateway.cost_by_team()
    assert totals["credit"] > totals["treasury"] or totals["credit"] > 0
    assert set(totals) == {"credit", "treasury"}


def test_catalog_covers_registered_models():
    for model_id in MODEL_CATALOG:
        assert MODEL_CATALOG[model_id]["cost_per_1k_input"] > 0
