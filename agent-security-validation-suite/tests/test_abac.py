"""Tests for the ABAC / CARDS attribute-repository module."""

from agent_security.abac import (
    AttributeRepository, Decision, PolicyEngine, PolicyRule, Resource,
    Subject, run_abac_suite,
)


def _engine():
    repo = AttributeRepository()
    repo.add_subject(Subject("alice", "identity", "confidential", mfa=True))
    repo.add_subject(Subject("bob", "payments", "confidential", mfa=True))
    repo.add_subject(Subject("carol", "identity", "internal"))
    repo.add_subject(Subject("dave", "identity", "confidential",
                             employment_type="contractor", mfa=True))
    repo.add_resource(Resource("cards:attrs:alice", "identity",
                               "confidential",
                               sensitive_fields=frozenset({"ssn"})))
    repo.add_resource(Resource("cards:attrs:bob", "payments", "internal"))
    repo.add_resource(Resource("cards:keys:root", "identity", "restricted"))
    repo.add_resource(Resource("cards:attrs:stale", "identity", "internal",
                               stale_attributes=True))
    return PolicyEngine(repository=repo)


def test_same_team_read_allowed():
    engine = _engine()
    decision = engine.decide_by_id("alice", "cards:attrs:alice", "read")
    assert decision.allowed is True
    assert decision.rule == "allow-same-team-read"


def test_cross_team_confidential_read_denied():
    engine = _engine()
    decision = engine.decide_by_id("bob", "cards:attrs:alice", "read")
    assert decision.allowed is False
    assert decision.rule == "default-deny"


def test_cross_team_internal_read_allowed():
    engine = _engine()
    decision = engine.decide_by_id("alice", "cards:attrs:bob", "read")
    assert decision.allowed is True
    assert decision.rule == "allow-cross-team-read"


def test_low_clearance_read_denied():
    engine = _engine()
    decision = engine.decide_by_id("carol", "cards:attrs:alice", "read")
    assert decision.allowed is False


def test_write_requires_mfa():
    engine = _engine()
    decision = engine.decide_by_id("carol", "cards:attrs:alice", "write")
    assert decision.allowed is False


def test_write_allowed_with_mfa_same_team():
    engine = _engine()
    decision = engine.decide_by_id("alice", "cards:attrs:alice", "write")
    assert decision.allowed is True
    assert decision.rule == "allow-same-team-write"


def test_restricted_denied_for_contractor_and_service():
    engine = _engine()
    for principal in ("dave",):
        decision = engine.decide_by_id(principal, "cards:keys:root", "read")
        assert decision.allowed is False
        assert decision.rule == "deny-restricted-to-contractors"


def test_stale_attributes_force_deny_then_refresh_allows():
    engine = _engine()
    before = engine.decide_by_id("alice", "cards:attrs:stale", "read")
    assert before.allowed is False
    assert before.rule == "deny-stale-attributes"
    assert engine.repository.refresh("cards:attrs:stale") is True
    after = engine.decide_by_id("alice", "cards:attrs:stale", "read")
    assert after.allowed is True


def test_unknown_subject_and_resource_denied():
    engine = _engine()
    assert engine.decide_by_id("mallory", "cards:attrs:alice",
                               "read").allowed is False
    assert engine.decide_by_id("alice", "cards:attrs:missing",
                               "read").allowed is False


def test_sensitive_field_denied_without_mfa_but_request_allowed():
    engine = _engine()
    repo = engine.repository
    repo.add_subject(Subject("erin", "identity", "confidential",
                             mfa=False))
    decision = engine.decide_by_id("erin", "cards:attrs:alice", "read",
                                   ("name", "ssn"))
    assert decision.allowed is True
    assert decision.fields_denied == ("ssn",)


def test_sensitive_field_allowed_with_mfa_same_team():
    engine = _engine()
    decision = engine.decide_by_id("alice", "cards:attrs:alice", "read",
                                   ("name", "ssn"))
    assert decision.allowed is True
    assert decision.fields_denied == ()


def test_custom_deny_rule_wins_over_allow():
    engine = PolicyEngine(rules=[
        PolicyRule("deny-payments-write", "write", "deny", same_team=True),
        PolicyRule("allow-any-write", "write", "allow"),
    ])
    subject = Subject("bob", "payments", "confidential", mfa=True)
    resource = Resource("cards:attrs:bob", "payments", "internal")
    decision = engine.decide(subject, resource, "write")
    assert decision.allowed is False
    assert decision.rule == "deny-payments-write"


def test_abac_suite_all_scenarios_pass():
    rows, allowed, denied = run_abac_suite()
    assert all(r["passed"] for r in rows), rows
    assert len(rows) == 13
    assert allowed + denied == 13
