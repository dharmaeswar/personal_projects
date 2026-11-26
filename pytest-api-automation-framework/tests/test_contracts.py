"""Tests for the qaops.contracts JSON contract validator.

The validator itself is checked in isolation (missing keys, wrong types,
out-of-range numbers, bad enums, nested objects, array items), then
applied to live API payloads: every plan and every trade in a page must
satisfy its declared contract. A contract failure is a test failure,
never an error, so a schema break shows up as a readable violation list.
"""
import pytest

from qaops.contracts import check, validate

PLAN_CONTRACT = {
    "type": "object",
    "required": ["id", "name", "price", "data_gb"],
    "properties": {
        "id": {"type": "integer", "min": 1},
        "name": {"type": "string", "min_length": 1},
        "price": {"type": "number", "min": 0},
        "data_gb": {"type": "integer", "min": 1},
    },
}

TRADE_CONTRACT = {
    "type": "object",
    "required": ["id", "symbol", "side", "price", "qty", "ts"],
    "properties": {
        "id": {"type": "integer", "min": 1},
        "symbol": {"type": "string", "pattern": "^[A-Z]+$"},
        "side": {"type": "string", "enum": ["BUY", "SELL"]},
        "price": {"type": "number", "min": 0},
        "qty": {"type": "integer", "min": 1, "max": 1000},
        "ts": {"type": "integer", "min": 1},
    },
}


def test_valid_payload_passes():
    assert check({"id": 1, "name": "Basic", "price": 20.0, "data_gb": 5},
                 PLAN_CONTRACT) is True
    assert validate({"id": 1, "name": "Basic", "price": 20.0, "data_gb": 5},
                    PLAN_CONTRACT) == []


def test_missing_required_key_is_a_violation():
    violations = validate({"id": 1, "name": "Basic"}, PLAN_CONTRACT)
    assert any("price" in v for v in violations)
    assert any("data_gb" in v for v in violations)


def test_wrong_type_is_a_violation():
    violations = validate(
        {"id": "1", "name": "Basic", "price": 20.0, "data_gb": 5},
        PLAN_CONTRACT)
    assert any("integer" in v for v in violations)


def test_out_of_range_number_is_a_violation():
    violations = validate(
        {"id": 1, "name": "Basic", "price": -5.0, "data_gb": 5},
        PLAN_CONTRACT)
    assert any("below minimum" in v for v in violations)


def test_bad_enum_and_pattern_are_violations():
    trade = {"id": 1, "symbol": "aapl", "side": "HOLD",
             "price": 10.0, "qty": 5, "ts": 100}
    violations = validate(trade, TRADE_CONTRACT)
    assert any("HOLD" in v for v in violations)
    assert any("aapl" in v for v in violations)


def test_nested_and_array_contracts():
    contract = {"type": "object", "required": ["plans"],
                "properties": {"plans": {"type": "array", "min_length": 1,
                                         "items": PLAN_CONTRACT}}}
    good = {"plans": [{"id": 1, "name": "Basic", "price": 20.0, "data_gb": 5}]}
    assert check(good, contract) is True
    bad = {"plans": [{"id": 1, "name": "Basic", "price": 20.0}]}
    violations = validate(bad, contract)
    assert any("data_gb" in v for v in violations)


def test_bool_is_not_an_integer():
    violations = validate(True, {"type": "integer"})
    assert violations != []


def test_live_plan_payloads_satisfy_contract(api_server):
    import json
    import urllib.request

    with urllib.request.urlopen(api_server + "/plans", timeout=5) as resp:
        body = json.loads(resp.read())
    for plan in body["plans"]:
        assert validate(plan, PLAN_CONTRACT) == []


def test_live_trade_page_satisfies_contract(api_server):
    import json
    import urllib.request

    with urllib.request.urlopen(api_server + "/trades?limit=100&offset=0",
                                timeout=5) as resp:
        body = json.loads(resp.read())
    assert body["total"] == 5000
    for trade in body["trades"]:
        assert validate(trade, TRADE_CONTRACT) == [], trade
