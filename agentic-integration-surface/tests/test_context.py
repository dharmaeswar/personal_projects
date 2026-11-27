"""Tests: caller context propagation and authorization."""

import pytest

from integration_surface.context import CallerContext, ContextError


def _ctx():
    return CallerContext(
        user_id="u1", tenant_id="t1",
        scopes=frozenset({"amp:read"}), auth_mechanism="oauth",
    )


def test_require_scopes_passes_when_held():
    _ctx().require_scopes("amp:read")


def test_require_scopes_fails_on_missing():
    with pytest.raises(ContextError, match="lacks scopes: amp:migrate"):
        _ctx().require_scopes("amp:read", "amp:migrate")


def test_child_propagates_identity_but_not_privilege():
    child = _ctx().child(request_id="r-1", trace_id="tr-1")
    assert child.user_id == "u1"
    assert child.tenant_id == "t1"
    assert child.scopes == frozenset({"amp:read"})
    assert child.request_id == "r-1"
    assert child.trace_id == "tr-1"
    # A child context never gains scopes.
    with pytest.raises(ContextError):
        child.require_scopes("amp:migrate")


def test_tenant_context_is_immutable():
    with pytest.raises(ContextError, match="tenant context is immutable"):
        _ctx().for_tenant("t2")
