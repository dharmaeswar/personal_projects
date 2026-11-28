"""Tests for the OpenFGA-style authorization model and tuple store."""

import pytest

from actions_runtime import ActionsService
from actions_runtime.authz import AuthorizationModel, AuthorizationStore, ciam_model


def make_store():
    return AuthorizationStore(ciam_model())


def test_direct_tuple_grants_relation():
    store = make_store()
    store.write_tuple("user:u1", "viewer", "resource:report-7")
    assert store.check("user:u1", "viewer", "resource:report-7") is True
    assert store.check("user:u2", "viewer", "resource:report-7") is False


def test_union_rewrite_editor_includes_viewer():
    store = make_store()
    store.write_tuple("user:u1", "viewer", "resource:report-7")
    assert store.check("user:u1", "editor", "resource:report-7") is True
    assert store.check("user:u1", "admin", "resource:report-7") is True


def test_editor_does_not_imply_viewer_downwards():
    store = make_store()
    store.write_tuple("user:u1", "editor", "resource:report-7")
    assert store.check("user:u1", "viewer", "resource:report-7") is False


def test_delete_tuple_revokes_access():
    store = make_store()
    store.write_tuple("user:u1", "viewer", "resource:report-7")
    assert store.delete_tuple("user:u1", "viewer", "resource:report-7") is True
    assert store.check("user:u1", "viewer", "resource:report-7") is False
    assert store.delete_tuple("user:u1", "viewer", "resource:report-7") is False


def test_group_membership_grants_relation():
    store = make_store()
    store.add_group_member("group:eng", "user:u1")
    store.write_tuple("group:eng", "viewer", "resource:report-7")
    assert store.check("user:u1", "viewer", "resource:report-7") is True
    assert store.check("user:u2", "viewer", "resource:report-7") is False
    store.remove_group_member("group:eng", "user:u1")
    assert store.check("user:u1", "viewer", "resource:report-7") is False


def test_cyclic_model_fails_closed_not_loops():
    model = AuthorizationModel()
    model.define("resource", "a", kind="union", members=("b",))
    model.define("resource", "b", kind="union", members=("a",))
    store = AuthorizationStore(model)
    assert store.check("user:u1", "a", "resource:r1") is False


def test_unknown_relation_is_denied():
    store = make_store()
    store.write_tuple("user:u1", "viewer", "resource:report-7")
    assert store.check("user:u1", "owner", "resource:report-7") is False


def test_list_objects_returns_only_allowed():
    store = make_store()
    store.write_tuple("user:u1", "viewer", "resource:report-7")
    store.write_tuple("user:u1", "viewer", "resource:report-9")
    store.write_tuple("user:u2", "viewer", "resource:report-8")
    assert store.list_objects("user:u1", "viewer", "resource") == [
        "resource:report-7", "resource:report-9",
    ]


def test_service_authorize_is_tenant_scoped_and_audited():
    svc = ActionsService()
    svc.create_tenant("acme", "Acme Corp")
    svc.authz.write_tuple("user:u1", "viewer", "resource:report-7")
    result = svc.authorize("acme", "user:u1", "viewer", "resource:report-7")
    assert result["allowed"] is True
    assert svc.audit.entries[-1].outcome == "allow"
    denied = svc.authorize("acme", "user:u2", "viewer", "resource:report-7")
    assert denied["allowed"] is False
    with pytest.raises(ValueError):
        svc.authorize("globex", "user:u1", "viewer", "resource:report-7")
