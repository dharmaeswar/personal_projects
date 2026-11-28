"""MCP-style tool definitions: the tools an agent is allowed to call.

Each tool carries a JSON schema for its arguments.  `dispatch` validates
the arguments against that schema *before* any service call runs, so a
malformed or out-of-range call fails fast with a plain-language error and
never reaches the payment path.  This is the MCP-style integration shape
the role names: structured tool calls, validated arguments, and an audit
trail for every call.
"""

from __future__ import annotations

from .checkout import CheckoutService, Receipt


TOOL_SCHEMAS: dict[str, dict] = {
    "create_checkout": {
        "type": "object",
        "required": ["agent_id", "user_id", "merchant_id", "amount_cents",
                     "currency", "idempotency_key"],
        "properties": {
            "agent_id": {"type": "string"},
            "user_id": {"type": "string"},
            "merchant_id": {"type": "string"},
            "amount_cents": {"type": "integer", "minimum": 1},
            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
            "idempotency_key": {"type": "string", "minLength": 1},
        },
    },
    "authorize_payment": {
        "type": "object",
        "required": ["order_id", "card_number", "idempotency_key"],
        "properties": {
            "order_id": {"type": "string"},
            "card_number": {"type": "string", "minLength": 13, "maxLength": 19},
            "idempotency_key": {"type": "string", "minLength": 1},
        },
    },
    "capture_payment": {
        "type": "object",
        "required": ["order_id", "idempotency_key"],
        "properties": {
            "order_id": {"type": "string"},
            "idempotency_key": {"type": "string", "minLength": 1},
        },
    },
    "refund_payment": {
        "type": "object",
        "required": ["order_id", "amount_cents", "idempotency_key"],
        "properties": {
            "order_id": {"type": "string"},
            "amount_cents": {"type": "integer", "minimum": 1},
            "idempotency_key": {"type": "string", "minLength": 1},
        },
    },
    "get_transaction_status": {
        "type": "object",
        "required": ["order_id"],
        "properties": {"order_id": {"type": "string"}},
    },
}


class ToolCallError(ValueError):
    """Raised when a tool call fails schema validation."""


def validate_args(tool_name: str, args: dict) -> list[str]:
    """Check args against the tool's schema; empty list means valid."""
    schema = TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        return [f"unknown tool {tool_name!r}"]
    problems: list[str] = []
    for name in schema["required"]:
        if name not in args:
            problems.append(f"missing required argument {name!r}")
    for name, spec in schema["properties"].items():
        if name not in args:
            continue
        value = args[name]
        if spec["type"] == "string" and not isinstance(value, str):
            problems.append(f"{name!r} must be a string")
        if spec["type"] == "integer" and not isinstance(value, int):
            problems.append(f"{name!r} must be an integer")
        if isinstance(value, str):
            if "minLength" in spec and len(value) < spec["minLength"]:
                problems.append(f"{name!r} is too short")
            if "maxLength" in spec and len(value) > spec["maxLength"]:
                problems.append(f"{name!r} is too long")
        if isinstance(value, int) and "minimum" in spec and value < spec["minimum"]:
            problems.append(f"{name!r} must be at least {spec['minimum']}")
    return problems


def dispatch(tool_name: str, args: dict, service: CheckoutService,
             token_str: str = "") -> Receipt | dict:
    """Validate, then run one tool call.  Raises ToolCallError on bad args."""
    problems = validate_args(tool_name, args)
    if problems:
        raise ToolCallError(f"{tool_name}: " + "; ".join(problems))
    if tool_name == "capture_payment":
        return service.capture(args["order_id"], args["idempotency_key"])
    if tool_name == "refund_payment":
        return service.refund(args["order_id"], args["amount_cents"],
                              args["idempotency_key"])
    if tool_name == "get_transaction_status":
        order = service.get_order(args["order_id"])
        return {"order_id": order.order_id, "status": order.status,
                "amount_cents": order.amount_cents,
                "currency": order.currency,
                "captured_cents": order.captured_cents,
                "refunded_cents": order.refunded_cents}
    if tool_name == "authorize_payment":
        return service.authorize(args["order_id"], args["card_number"],
                                 token_str, args["idempotency_key"])
    raise ToolCallError(f"{tool_name} needs a checkout intent; call the service directly")
