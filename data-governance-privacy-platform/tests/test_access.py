"""Tests for RBAC + purpose-based access evaluation."""

import pytest

from governance.access import AccessEvaluator, AccessRequest
from governance.catalog import Catalog, Column, Dataset


def _catalog() -> Catalog:
    catalog = Catalog()
    catalog.register(Dataset(
        name="members", owner_team="member-platform", system="Snowflake",
        retention_days=730, legal_hold=False,
        columns=[
            Column("member_id", "string", sensitivity="internal"),
            Column("email", "string", sensitivity="confidential"),
            Column("ssn", "string", sensitivity="restricted"),
        ],
        rows=[],
    ))
    catalog.register(Dataset(
        name="loan_applications", owner_team="lending", system="Postgres",
        retention_days=1095, legal_hold=True,
        columns=[
            Column("credit_score", "integer", sensitivity="confidential"),
            Column("ssn", "string", sensitivity="restricted"),
        ],
        rows=[],
    ))
    return catalog


@pytest.fixture
def evaluator() -> AccessEvaluator:
    return AccessEvaluator(_catalog())


def test_admin_can_read_restricted(evaluator):
    d = evaluator.evaluate(AccessRequest("admin", "operations", "members", ["ssn"]))
    assert d.allowed is True
    assert d.masked is False


def test_analyst_can_read_confidential(evaluator):
    d = evaluator.evaluate(AccessRequest("analyst", "reporting", "members", ["email"]))
    assert d.allowed is True


def test_analyst_cannot_read_restricted(evaluator):
    d = evaluator.evaluate(AccessRequest("analyst", "reporting", "members", ["ssn"]))
    assert d.allowed is False
    assert "restricted" in d.reason


def test_auditor_cannot_read_restricted(evaluator):
    d = evaluator.evaluate(AccessRequest("auditor", "audit", "members", ["ssn"]))
    assert d.allowed is False


def test_auditor_allowed_but_masked(evaluator):
    d = evaluator.evaluate(AccessRequest("auditor", "audit", "members", ["email"]))
    assert d.allowed is True
    assert d.masked is True


def test_legal_hold_blocks_model_training_for_every_role(evaluator):
    for role in ("admin", "data-engineer", "analyst", "auditor"):
        d = evaluator.evaluate(
            AccessRequest(role, "model-training", "loan_applications", ["credit_score"]))
        assert d.allowed is False
        assert "legal hold" in d.reason


def test_legal_hold_does_not_block_reporting(evaluator):
    d = evaluator.evaluate(
        AccessRequest("analyst", "reporting", "loan_applications", ["credit_score"]))
    assert d.allowed is True


def test_support_purpose_cannot_read_restricted(evaluator):
    d = evaluator.evaluate(AccessRequest("data-engineer", "support", "members", ["ssn"]))
    assert d.allowed is False
    assert "support" in d.reason


def test_unknown_role_denied(evaluator):
    d = evaluator.evaluate(AccessRequest("intern", "reporting", "members", ["member_id"]))
    assert d.allowed is False
    assert "unknown role" in d.reason


def test_unknown_dataset_denied(evaluator):
    d = evaluator.evaluate(AccessRequest("admin", "reporting", "nope", ["member_id"]))
    assert d.allowed is False


def test_unknown_column_denied(evaluator):
    d = evaluator.evaluate(AccessRequest("admin", "reporting", "members", ["nope"]))
    assert d.allowed is False


def test_every_decision_is_logged(evaluator):
    evaluator.evaluate(AccessRequest("admin", "reporting", "members", ["member_id"]))
    evaluator.evaluate(AccessRequest("analyst", "reporting", "members", ["ssn"]))
    assert len(evaluator.log) == 2
    assert evaluator.log[0].decision.allowed is True
    assert evaluator.log[1].decision.allowed is False
