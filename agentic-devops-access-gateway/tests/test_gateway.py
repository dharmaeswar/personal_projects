import pytest

from gateway import AccessGateway


@pytest.fixture
def gw():
    gateway = AccessGateway()
    gateway.registry.register("srv-prod-1", "prod-1", "prod", "10.0.1.21:22")
    gateway.registry.register("srv-stage-1", "stage-1", "staging", "10.0.2.14:22")
    return gateway


def _deployer(gw):
    return gw.tokens.issue("agent-deploy-1", "deployer",
                           ["deploy:service:checkout", "read:service:checkout"],
                           "prod")


def test_happy_path_executes_and_audits(gw):
    r = gw.execute(_deployer(gw), "deploy", "service:checkout", "srv-prod-1")
    assert r.allowed is True
    assert "checkout" in r.result
    assert len(gw.executed_actions) == 1
    assert len(gw.audit) == 1
    assert gw.audit.entries()[0].decision == "allowed"


def test_out_of_scope_action_denied_and_audited(gw):
    token = gw.tokens.issue("agent-ops-1", "operator",
                            ["read:service:checkout"], "prod")
    r = gw.execute(token, "deploy", "service:checkout", "srv-prod-1")
    assert r.allowed is False
    assert "scope" in r.reason
    assert gw.executed_actions == []
    assert gw.audit.denials()[0].actor == "agent-ops-1"


def test_role_policy_denial_even_with_token_scope(gw):
    # Token scope covers the action, but the operator role policy does not.
    token = gw.tokens.issue("agent-ops-1", "operator",
                            ["deploy:service:checkout"], "prod")
    r = gw.execute(token, "deploy", "service:checkout", "srv-prod-1")
    assert r.allowed is False
    assert "role" in r.reason


def test_expired_token_denied(gw):
    token = gw.tokens.issue("agent-1", "deployer",
                            ["deploy:service:checkout"], "prod",
                            ttl_seconds=10, now=1000.0)
    # verify() uses real time by default; simulate expiry via a short token
    # issued in the past: issue at now=1000, gateway verify uses time.time(),
    # which is far past expiry, so the token is expired.
    r = gw.execute(token, "deploy", "service:checkout", "srv-prod-1")
    assert r.allowed is False
    assert "expired" in r.reason


def test_revoked_token_denied(gw):
    token = _deployer(gw)
    gw.tokens.revoke(gw.tokens.token_id(token))
    r = gw.execute(token, "deploy", "service:checkout", "srv-prod-1")
    assert r.allowed is False
    assert "revoked" in r.reason


def test_unhealthy_server_denied(gw):
    gw.registry.mark_unhealthy("srv-prod-1")
    r = gw.execute(_deployer(gw), "deploy", "service:checkout", "srv-prod-1")
    assert r.allowed is False
    assert "unhealthy" in r.reason


def test_unknown_server_denied(gw):
    r = gw.execute(_deployer(gw), "deploy", "service:checkout", "srv-nope")
    assert r.allowed is False
    assert "unknown remote server" in r.reason


def test_wrong_environment_denied(gw):
    r = gw.execute(_deployer(gw), "deploy", "service:checkout", "srv-stage-1")
    assert r.allowed is False
    assert "staging" in r.reason


def test_idempotent_retry_does_not_reexecute(gw):
    token = _deployer(gw)
    first = gw.execute(token, "deploy", "service:checkout", "srv-prod-1",
                       idempotency_key="req-1")
    second = gw.execute(token, "deploy", "service:checkout", "srv-prod-1",
                        idempotency_key="req-1")
    assert first.allowed and second.allowed
    assert second.replayed is True
    assert len(gw.executed_actions) == 1
    assert len(gw.audit) == 1  # replay is not a new audit entry


def test_different_idempotency_key_executes_again(gw):
    token = _deployer(gw)
    gw.execute(token, "deploy", "service:checkout", "srv-prod-1",
               idempotency_key="req-1")
    gw.execute(token, "deploy", "service:checkout", "srv-prod-1",
               idempotency_key="req-2")
    assert len(gw.executed_actions) == 2


def test_malformed_token_denied_and_audited(gw):
    r = gw.execute("garbage", "read", "service:checkout", "srv-prod-1")
    assert r.allowed is False
    assert len(gw.audit.denials()) == 1
