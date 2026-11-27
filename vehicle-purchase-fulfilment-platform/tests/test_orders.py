"""Tests for the order lifecycle and pricing (orders.py)."""

import pytest

from vehicle_platform.orders import (
    DOC_FEE_CENTS,
    DELIVERY_FEE_CENTS,
    Order,
    OrderError,
    rebuild_from_events,
    validate_new_order,
)

GOOD = {
    "order_id": "ORD-1",
    "vin": "1HGCM82633A004352",
    "customer_id": "CUST-1",
    "list_price_cents": 2_450_000,
    "state_code": "AZ",
    "delivery_zip": "85281",
}


def test_create_valid_order():
    order = validate_new_order(dict(GOOD))
    assert order.status == "RESERVED"
    assert order.total_cents() == 2_733_102  # 2450000 + 59900 + 19900 + 203302 tax


def test_total_uses_decimal_rounding():
    # Taxable 2,509,900 x 8.1% = 203,301.9 -> rounds to 203,302 (half up).
    order = validate_new_order(dict(GOOD))
    tax = order.total_cents() - 2_450_000 - DOC_FEE_CENTS - DELIVERY_FEE_CENTS
    assert tax == 203_302


def test_bad_vin_rejected():
    for vin in ("SHORT", "1HGCM82633A00435I", "1hgcm82633a004352", ""):
        bad = dict(GOOD, vin=vin)
        with pytest.raises(OrderError):
            validate_new_order(bad)


def test_bad_zip_and_state_rejected():
    with pytest.raises(OrderError):
        validate_new_order(dict(GOOD, delivery_zip="8528"))
    with pytest.raises(OrderError):
        validate_new_order(dict(GOOD, state_code="ZZ"))
    with pytest.raises(OrderError):
        validate_new_order(dict(GOOD, list_price_cents=0))


def test_forward_transitions():
    order = validate_new_order(dict(GOOD))
    for state in ("INSPECTED", "FINANCED", "DELIVERY_SCHEDULED", "DELIVERED"):
        order.advance(state)
    assert order.status == "DELIVERED"


def test_illegal_transition_rejected():
    order = validate_new_order(dict(GOOD))
    with pytest.raises(OrderError):
        order.advance("FINANCED")  # skips INSPECTED
    with pytest.raises(OrderError):
        order.advance("DELIVERED")


def test_cancel_from_any_pre_delivery_state():
    order = validate_new_order(dict(GOOD))
    order.advance("INSPECTED")
    order.advance("CANCELLED")
    assert order.status == "CANCELLED"
    with pytest.raises(OrderError):
        order.advance("FINANCED")


def test_delivered_order_cannot_be_cancelled():
    order = validate_new_order(dict(GOOD))
    for state in ("INSPECTED", "FINANCED", "DELIVERY_SCHEDULED", "DELIVERED"):
        order.advance(state)
    with pytest.raises(OrderError):
        order.advance("CANCELLED")


def test_rebuild_from_events():
    events = [
        {"payload": {"type": "ORDER_CREATED", **GOOD, "status": "RESERVED"}},
        {"payload": {"type": "ORDER_ADVANCED", **GOOD, "status": "INSPECTED"}},
        {"payload": {"type": "ORDER_ADVANCED", **GOOD, "status": "FINANCED"}},
    ]
    order = rebuild_from_events("ORD-1", events)
    assert order is not None
    assert order.status == "FINANCED"
    assert order.events_applied == 3
    assert order.total_cents() == 2_733_102


def test_rebuild_empty_log_returns_none():
    assert rebuild_from_events("ORD-1", []) is None
