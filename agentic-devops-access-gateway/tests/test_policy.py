import pytest

from gateway import PolicyEngine


@pytest.fixture
def engine():
    return PolicyEngine()


def test_deployer_can_deploy_service(engine):
    assert engine.allowed("deployer", "deploy", "service:checkout")


def test_deployer_cannot_delete(engine):
    assert not engine.allowed("deployer", "delete", "service:checkout")


def test_operator_cannot_deploy(engine):
    assert not engine.allowed("operator", "deploy", "service:checkout")


def test_operator_can_restart_web_service_only(engine):
    assert engine.allowed("operator", "restart", "service:web-api")
    assert not engine.allowed("operator", "restart", "service:db-primary")


def test_reviewer_read_only_plus_approve(engine):
    assert engine.allowed("reviewer", "read", "service:checkout")
    assert engine.allowed("reviewer", "approve", "deploy:checkout-v2")
    assert not engine.allowed("reviewer", "deploy", "service:checkout")


def test_admin_wildcard_allows_anything(engine):
    assert engine.allowed("admin", "delete", "secrets:vault")
    assert engine.allowed("admin", "deploy", "service:anything")


def test_unknown_role_denied_everything(engine):
    assert not engine.allowed("guest", "read", "service:checkout")


def test_wildcard_resource_pattern(engine):
    assert engine.allowed("deployer", "read", "logs:checkout-2026-11-23")
    assert not engine.allowed("deployer", "read", "secrets:vault")
