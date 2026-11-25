import pytest

from sdlc_agents.tools import Tool, ToolServer


def make_server() -> ToolServer:
    server = ToolServer()
    server.register(Tool("echo", "Echo a message", {"msg": "string"}, ["msg"],
                         lambda a: {"echo": a["msg"]}, cost_per_call=0.01))
    server.register(Tool("add", "Add two ints", {"a": "integer", "b": "integer"},
                         ["a", "b"], lambda a: a["a"] + a["b"]))
    return server


def test_call_validates_and_dispatches():
    assert make_server().call("echo", {"msg": "hi"}) == {"echo": "hi"}


def test_call_missing_required_param_fails():
    with pytest.raises(ValueError, match="missing required"):
        make_server().call("add", {"a": 1})


def test_call_wrong_type_fails():
    with pytest.raises(ValueError, match="must be integer"):
        make_server().call("add", {"a": "1", "b": 2})


def test_call_unknown_tool_fails():
    with pytest.raises(ValueError, match="unknown tool"):
        make_server().call("nope", {})


def test_call_unexpected_param_fails():
    with pytest.raises(ValueError, match="unexpected parameter"):
        make_server().call("echo", {"msg": "hi", "extra": 1})


def test_trace_records_failed_calls_too():
    server = make_server()
    server.call("echo", {"msg": "hi"})
    with pytest.raises(ValueError):
        server.call("add", {"a": 1})
    totals = server.totals()
    assert totals["calls"] == 2
    assert totals["failed_calls"] == 1
    assert totals["total_cost"] == 0.01
    assert totals["calls_by_tool"] == {"add": 1, "echo": 1}
