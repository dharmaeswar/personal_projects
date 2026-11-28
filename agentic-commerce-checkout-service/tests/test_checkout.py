"""Tests: checkout flow, idempotency, refunds, audit chain, MCP tools."""

from datetime import datetime, timedelta, timezone

import pytest

from agentic_checkout.api import TEST_CARD, build_service
from agentic_checkout.checkout import CheckoutError
from agentic_checkout.intent import AgentIntent
from agentic_checkout.mcp_tools import (
    TOOL_SCHEMAS, ToolCallError, dispatch, validate_args,
)
from agentic_checkout.tokens import issue_token

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def _setup():
    service = build_service()
    token = issue_token(
        agent_id="agent_shopper_01", user_id="user_001",
        scopes=["checkout.create", "payment.authorize", "payment.capture"],
        merchant_allowlist=["merchant_books"],
        max_amount_cents=200_00,
        expires_at=NOW + timedelta(hours=1),
        secret=b"demo-only-secret-do-not-use-in-production",
    )
    return service, token


def _intent(**overrides):
    base = dict(agent_id="agent_shopper_01", user_id="user_001",
                merchant_id="merchant_books", action="checkout.create",
                amount_cents=4999, currency="USD", idempotency_key="k-1")
    base.update(overrides)
    return AgentIntent(**base)


def test_full_purchase_flow_end_to_end():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    assert order.status == "CREATED"
    receipt = service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)
    assert receipt.status == "AUTHORIZED"
    receipt = service.capture(order.order_id, "k-3", NOW)
    assert receipt.status == "CAPTURED"
    assert service.get_order(order.order_id).captured_cents == 4999
    assert service.audit.verify_chain() is True


def test_capture_is_idempotent_no_double_charge():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)
    first = service.capture(order.order_id, "k-3", NOW)
    second = service.capture(order.order_id, "k-3", NOW)
    assert second.replayed is True
    assert first.amount_cents == second.amount_cents
    assert service.get_order(order.order_id).captured_cents == 4999


def test_over_cap_intent_rejected_with_no_order():
    service, token = _setup()
    with pytest.raises(CheckoutError, match="cap"):
        service.create_checkout(_intent(amount_cents=999_99), token, NOW)
    with pytest.raises(CheckoutError, match="unknown order"):
        service.get_order("ord_000001")


def test_wrong_merchant_intent_rejected():
    service, token = _setup()
    with pytest.raises(CheckoutError, match="allowlist"):
        service.create_checkout(_intent(merchant_id="merchant_other"), token, NOW)


def test_risk_denied_checkout_for_blocked_merchant():
    service, token = _setup()
    service._risk.blocked_merchants = frozenset({"merchant_books"})
    with pytest.raises(CheckoutError, match="risk denied"):
        service.create_checkout(_intent(), token, NOW)


def test_replayed_authorization_is_refused():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)
    with pytest.raises(CheckoutError, match="replayed"):
        service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)


def test_capture_before_authorize_is_refused():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    with pytest.raises(CheckoutError, match="not AUTHORIZED"):
        service.capture(order.order_id, "k-9", NOW)


def test_refund_partial_then_full():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)
    service.capture(order.order_id, "k-3", NOW)
    partial = service.refund(order.order_id, 2000, "k-4")
    assert partial.status == "CAPTURED"
    full = service.refund(order.order_id, 2999, "k-5")
    assert full.status == "REFUNDED"
    with pytest.raises(CheckoutError, match="refundable balance"):
        service.refund(order.order_id, 1, "k-6")


def test_audit_chain_detects_tampering():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)
    assert service.audit.verify_chain() is True
    entries = service.audit.entries()
    tampered = entries[0]
    object.__setattr__(tampered, "outcome", "forged outcome")
    assert service.audit.verify_chain() is False


def test_mcp_tool_schema_validation():
    assert validate_args("capture_payment", {"order_id": "ord_1"}) == [
        "missing required argument 'idempotency_key'"]
    assert validate_args("capture_payment",
                          {"order_id": "ord_1", "idempotency_key": "k"}) == []
    assert validate_args("refund_payment",
                          {"order_id": "o", "amount_cents": 0,
                           "idempotency_key": "k"}) == [
        "'amount_cents' must be at least 1"]
    assert validate_args("no_such_tool", {}) == ["unknown tool 'no_such_tool'"]


def test_mcp_dispatch_runs_capture_and_status():
    service, token = _setup()
    order = service.create_checkout(_intent(), token, NOW)
    service.authorize(order.order_id, TEST_CARD, token, "k-2", NOW)
    receipt = dispatch("capture_payment",
                       {"order_id": order.order_id, "idempotency_key": "k-3"},
                       service)
    assert receipt.status == "CAPTURED"
    status = dispatch("get_transaction_status", {"order_id": order.order_id},
                      service)
    assert status["status"] == "CAPTURED"
    assert status["captured_cents"] == 4999
    with pytest.raises(ToolCallError):
        dispatch("capture_payment", {"order_id": order.order_id}, service)


def test_all_five_tools_have_schemas():
    assert set(TOOL_SCHEMAS) == {
        "create_checkout", "authorize_payment", "capture_payment",
        "refund_payment", "get_transaction_status",
    }
