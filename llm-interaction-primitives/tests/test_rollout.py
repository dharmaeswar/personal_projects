"""Tests for the rollout loop."""

from interaction_lib import Message, Session, run_rollout


def _session():
    session = Session()
    session.append(Message("system", "You are helpful."))
    session.append(Message("user", "What is 2 + 2?"))
    return session


def test_rollout_stops_on_stop_string():
    replies = iter(["The answer is 4. <|eos|>"])

    def sampler(messages):
        return next(replies)

    result = run_rollout(_session(), sampler, max_turns=4)
    assert result.turns == 1
    assert result.stopped_reason == "stop_string"
    assert result.transcript[-1].content == "The answer is 4. <|eos|>"


def test_rollout_stops_on_empty_reply():
    result = run_rollout(_session(), lambda messages: "", max_turns=4)
    assert result.turns == 0
    assert result.stopped_reason == "empty_reply"


def test_rollout_stops_at_max_turns():
    result = run_rollout(_session(), lambda messages: "keep going", max_turns=3)
    assert result.turns == 3
    assert result.stopped_reason == "max_turns"


def test_rollout_executes_tool_calls():
    def sampler(messages):
        if len(messages) == 2:
            return '```json\n{"name": "add", "arguments": {"a": 2, "b": 2}}\n```'
        return "Done. <|eos|>"

    def executor(call):
        return str(call.arguments["a"] + call.arguments["b"])

    result = run_rollout(_session(), sampler, executor=executor, max_turns=4)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "add"
    tool_messages = [m for m in result.transcript if m.role == "tool"]
    assert tool_messages == [Message("tool", "4")]


def test_rollout_without_executor_keeps_calls_unexecuted():
    def sampler(messages):
        return '```json\n{"name": "add", "arguments": {"a": 1, "b": 1}}\n```'

    result = run_rollout(_session(), sampler, max_turns=1)
    assert len(result.tool_calls) == 1
    assert all(m.role != "tool" for m in result.transcript)
