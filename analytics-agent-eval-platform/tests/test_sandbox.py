"""Tests for the sandboxed SQL execution and access controls."""

import pytest

from agent_eval.sandbox import Sandbox, SandboxError


@pytest.fixture
def sandbox():
    return Sandbox(role="analyst")


def test_describe_dataset_lists_tables_and_grain(sandbox):
    desc = sandbox.describe_dataset()
    assert desc["dataset_version"] == "community-analytics-v1"
    assert set(desc["tables"]) == {"communities", "posts"}
    assert desc["tables"]["posts"]["rows"] > 100


def test_select_query_returns_rows_and_provenance(sandbox):
    out = sandbox.run_query(
        "SELECT community, COUNT(*) AS n FROM posts GROUP BY community")
    assert out["columns"] == ["community", "n"]
    assert len(out["rows"]) == 5
    assert out["provenance"]["dataset_version"] == "community-analytics-v1"
    assert out["provenance"]["query_hash"]
    assert not out["truncated"]


def test_row_limit_truncates(sandbox):
    out = sandbox.run_query("SELECT id FROM posts", row_limit=5)
    assert out["truncated"] is True
    assert len(out["rows"]) == 5


def test_write_query_rejected(sandbox):
    with pytest.raises(SandboxError):
        sandbox.run_query("DELETE FROM posts WHERE id = 1")


def test_ddl_rejected(sandbox):
    with pytest.raises(SandboxError):
        sandbox.run_query("DROP TABLE posts")


def test_multi_statement_rejected(sandbox):
    with pytest.raises(SandboxError):
        sandbox.run_query("SELECT 1; SELECT 2")


def test_unknown_role_rejected():
    with pytest.raises(SandboxError):
        Sandbox(role="superuser")


def test_audit_trail_records_success_and_failure(sandbox):
    sandbox.run_query("SELECT COUNT(*) FROM posts")
    with pytest.raises(SandboxError):
        sandbox.run_query("SELECT * FROM posts WHERE bad_column = 1")
    assert len(sandbox.audit) == 2
    assert sandbox.audit[0]["ok"] is True
    assert sandbox.audit[1]["ok"] is False
    assert sandbox.audit[0]["query_hash"]


def test_seeded_data_is_deterministic():
    a = Sandbox()
    b = Sandbox()
    ra = a.run_query("SELECT SUM(score) FROM posts")["rows"]
    rb = b.run_query("SELECT SUM(score) FROM posts")["rows"]
    assert ra == rb
