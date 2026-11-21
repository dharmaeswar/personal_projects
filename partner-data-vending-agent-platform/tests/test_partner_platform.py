"""Tests for the partner data vending and agent skills platform."""

import pytest

from partner_platform.agent import PartnerAgent
from partner_platform.knowledge import KnowledgeBase
from partner_platform.models import HealthSample, ModelPlatform, ModelVersion
from partner_platform.skills import Skill, SkillRegistry
from partner_platform.vending import DataProduct, DataVending, Token


def _skill(name="campaign_insights", risk="low"):
    return Skill(
        name=name, version="1.0.0",
        description="Summarize campaign performance for an ads partner.",
        input_schema={"campaign_id": "string"},
        required_scopes=["campaigns:read"], risk=risk,
    )


def _product():
    return DataProduct(
        product_id="campaign-performance", name="Campaign Performance Daily",
        owner="ads-partner-data", required_scopes=["campaigns:read"],
        columns=["campaign_id", "spend_usd", "advertiser_email"],
        sensitive_columns=["advertiser_email"],
        rows=[{"campaign_id": "cmp-101", "spend_usd": 412.50,
               "advertiser_email": "partner@example.com"}],
    )


def _model(version="1.0.0"):
    return ModelVersion(
        model_name="spend-forecast", version=version, owner="ads-ml",
        tests_passed=True, eval_metrics={"mape": 0.08},
        rollback_plan={"version": "0.9.0", "steps": ["restore 0.9.0"]},
        on_call_primary="oncall-a", on_call_backup="oncall-b",
        deploy_window="09:00-17:00 ET weekdays",
    )


# --- skills ---------------------------------------------------------------

def test_skill_validation_rejects_bad_name_and_risk():
    bad = Skill(name="Bad Name", version="1.0", description="short",
                input_schema={}, required_scopes=[], risk="critical")
    problems = bad.validate()
    assert len(problems) >= 4


def test_low_risk_skill_invokes_without_approval():
    registry = SkillRegistry()
    registry.register(_skill())
    invocation = registry.invoke("campaign_insights", {"campaign_id": "cmp-101"})
    assert invocation.approved is True


def test_high_risk_skill_denied_without_approval():
    registry = SkillRegistry()
    registry.register(_skill(name="audience_export", risk="high"))
    invocation = registry.invoke("audience_export", {"campaign_id": "cmp-101"})
    assert invocation.approved is False
    assert "approval required" in invocation.result


def test_high_risk_skill_runs_with_approval():
    registry = SkillRegistry()
    registry.register(_skill(name="audience_export", risk="high"))
    invocation = registry.invoke("audience_export", {"campaign_id": "cmp-101"},
                                 approved_by="human-reviewer")
    assert invocation.approved is True
    assert invocation.approved_by == "human-reviewer"


def test_invoke_unknown_skill_raises():
    registry = SkillRegistry()
    with pytest.raises(KeyError):
        registry.invoke("nope", {})


def test_invoke_missing_input_raises():
    registry = SkillRegistry()
    registry.register(_skill())
    with pytest.raises(ValueError, match="missing inputs"):
        registry.invoke("campaign_insights", {})


def test_duplicate_skill_registration_rejected():
    registry = SkillRegistry()
    registry.register(_skill())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_skill())


# --- knowledge ------------------------------------------------------------

def test_retrieve_returns_cited_passage():
    kb = KnowledgeBase()
    kb.add_document("doc-1", "Guide",
                    "Campaign insights summarize impressions, clicks and spend.",
                    fresh_until="2027-01-01")
    results = kb.retrieve("how do campaign insights work")
    assert len(results) == 1
    assert results[0].passage.doc_id == "doc-1"
    assert results[0].stale is False


def test_retrieve_flags_stale_passages():
    kb = KnowledgeBase()
    kb.add_document("doc-1", "Guide", "Old campaign guidance text here.",
                    fresh_until="2026-01-01")
    results = kb.retrieve("campaign guidance")
    assert len(results) == 1
    assert results[0].stale is True
    assert kb.stale_count() == 1


def test_retrieve_empty_question_returns_nothing():
    kb = KnowledgeBase()
    kb.add_document("doc-1", "Guide", "Campaign insights text.",
                    fresh_until="2027-01-01")
    assert kb.retrieve("the and of") == []


def test_add_empty_document_rejected():
    kb = KnowledgeBase()
    with pytest.raises(ValueError):
        kb.add_document("doc-1", "Guide", "   ", fresh_until="2027-01-01")


# --- vending --------------------------------------------------------------

def test_vend_grants_scoped_token_and_masks_sensitive():
    vending = DataVending()
    vending.register(_product())
    token = Token("tok-1", "partner-app", ["campaigns:read"], "2027-01-01")
    result = vending.vend(token, "campaign-performance")
    assert result["granted"] is True
    assert result["rows"][0]["advertiser_email"] == "***MASKED***"
    assert result["rows"][0]["spend_usd"] == 412.50


def test_vend_unmasks_with_sensitive_scope():
    vending = DataVending()
    vending.register(_product())
    token = Token("tok-1", "partner-app",
                  ["campaigns:read", "sensitive:read"], "2027-01-01")
    result = vending.vend(token, "campaign-performance")
    assert result["rows"][0]["advertiser_email"] == "partner@example.com"


def test_vend_denies_missing_scope_and_audits():
    vending = DataVending()
    vending.register(_product())
    token = Token("tok-1", "partner-app", ["other:read"], "2027-01-01")
    result = vending.vend(token, "campaign-performance")
    assert result["granted"] is False
    assert vending.denied_count() == 1
    assert vending.audit_log[0].reason.startswith("missing scopes")


def test_vend_denies_expired_token():
    vending = DataVending()
    vending.register(_product())
    token = Token("tok-1", "partner-app", ["campaigns:read"], "2026-01-01")
    result = vending.vend(token, "campaign-performance")
    assert result["granted"] is False
    assert result["reason"] == "token expired"


def test_vend_unknown_product_denied():
    vending = DataVending()
    token = Token("tok-1", "partner-app", ["campaigns:read"], "2027-01-01")
    result = vending.vend(token, "no-such-product")
    assert result["granted"] is False


# --- models ---------------------------------------------------------------

def test_launch_blocked_when_tests_fail():
    platform = ModelPlatform()
    model = _model()
    model.tests_passed = False
    platform.register(model)
    result = platform.launch("spend-forecast", "1.0.0")
    assert result["launched"] is False
    assert "unit tests are not green" in result["blockers"]


def test_launch_blocked_without_rollback_plan():
    platform = ModelPlatform()
    model = _model()
    model.rollback_plan = {}
    platform.register(model)
    result = platform.launch("spend-forecast", "1.0.0")
    assert result["launched"] is False


def test_launch_succeeds_when_checklist_passes():
    platform = ModelPlatform()
    platform.register(_model())
    result = platform.launch("spend-forecast", "1.0.0")
    assert result["launched"] is True
    assert platform.live_version("spend-forecast") == "1.0.0"


def test_health_slo_flags_bad_latency():
    platform = ModelPlatform()
    bad = HealthSample("spend-forecast", "1.0.0", latency_ms=900, error_rate=0.01)
    assert platform.record_health(bad) is False
    good = HealthSample("spend-forecast", "1.0.0", latency_ms=120, error_rate=0.01)
    assert platform.record_health(good) is True


def test_rollback_returns_to_earlier_version():
    platform = ModelPlatform()
    platform.register(_model("1.0.0"))
    platform.register(_model("1.1.0"))
    platform.launch("spend-forecast", "1.0.0")
    platform.launch("spend-forecast", "1.1.0")
    result = platform.rollback("spend-forecast", "latency SLO breach")
    assert result["rolled_back"] is True
    assert result["to_version"] == "1.0.0"
    assert platform.live_version("spend-forecast") == "1.0.0"


# --- agent end to end -----------------------------------------------------

def _agent():
    skills = SkillRegistry()
    skills.register(_skill())
    kb = KnowledgeBase()
    kb.add_document("doc-1", "Guide",
                    "Campaign insights summarize impressions, clicks and spend.",
                    fresh_until="2027-01-01")
    vending = DataVending()
    vending.register(_product())
    models = ModelPlatform()
    models.register(_model())
    models.launch("spend-forecast", "1.0.0")
    return PartnerAgent(skills, kb, vending, models)


def test_agent_handles_request_end_to_end():
    agent = _agent()
    token = Token("tok-1", "partner-app", ["campaigns:read"], "2027-01-01")
    outcome = agent.handle_request(
        "campaign_insights", "campaign insights summary", token,
        {"campaign_id": "cmp-101"}, product_id="campaign-performance",
        model_name="spend-forecast")
    assert outcome["denied"] is None
    assert outcome["answer"] is not None
    assert len(outcome["rows"]) == 1
    assert [s["step"] for s in outcome["steps"]] == [
        "skill", "knowledge", "vending", "model"]


def test_agent_stops_when_vending_denied():
    agent = _agent()
    token = Token("tok-1", "partner-app", ["other:read"], "2027-01-01")
    outcome = agent.handle_request(
        "campaign_insights", "campaign insights summary", token,
        {"campaign_id": "cmp-101"}, product_id="campaign-performance",
        model_name="spend-forecast")
    assert outcome["denied"] is not None
    assert "vending denied" in outcome["denied"]
    assert outcome["answer"] is None


def test_agent_stops_when_only_stale_knowledge():
    agent = _agent()
    agent.knowledge = KnowledgeBase()
    agent.knowledge.add_document("doc-1", "Guide",
                                 "Campaign insights summarize impressions.",
                                 fresh_until="2026-01-01")
    token = Token("tok-1", "partner-app", ["campaigns:read"], "2027-01-01")
    outcome = agent.handle_request(
        "campaign_insights", "campaign insights summary", token,
        {"campaign_id": "cmp-101"})
    assert outcome["denied"] == "only stale knowledge available"
