"""The rollout loop: sample, parse tool calls, execute, repeat.

A rollout runs a sampler over a session until a stop string appears, the
turn budget is spent, or the sampler returns an empty reply. Tool calls in
a reply are executed through an injected executor and the results are
appended as tool messages, so the loop is fully testable with a fake
sampler and a fake executor — no model is needed to exercise it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .rendering import Message
from .session import Session
from .tool_calls import ToolCall, parse_tool_calls


@dataclass
class RolloutResult:
    """What one rollout produced: transcript, turns, stop reason, tokens."""

    transcript: list[Message]
    turns: int
    stopped_reason: str
    total_tokens: int
    tool_calls: list[ToolCall] = field(default_factory=list)


def run_rollout(
    session: Session,
    sampler: Callable[[list[Message]], str],
    executor: Callable[[ToolCall], str] | None = None,
    max_turns: int = 8,
    stop_strings: tuple[str, ...] = ("<|eos|>",),
) -> RolloutResult:
    """Run the rollout loop over ``session`` with an injected ``sampler``.

    Each turn appends the sampler's reply as an assistant message. If the
    reply contains tool calls and an ``executor`` is given, each call is
    executed and its result appended as a tool message. Stops on a stop
    string, an empty reply, or ``max_turns`` turns.
    """
    calls: list[ToolCall] = []
    turns = 0
    stopped_reason = "max_turns"
    while turns < max_turns:
        reply = sampler(list(session.messages))
        if not reply:
            stopped_reason = "empty_reply"
            break
        session.append(Message("assistant", reply))
        turns += 1
        if any(stop in reply for stop in stop_strings):
            stopped_reason = "stop_string"
            break
        found = parse_tool_calls(reply)
        calls.extend(found)
        if found and executor is not None:
            for call in found:
                result = executor(call)
                session.append(Message("tool", result))
    return RolloutResult(
        transcript=list(session.messages),
        turns=turns,
        stopped_reason=stopped_reason,
        total_tokens=session.token_count(),
        tool_calls=calls,
    )
