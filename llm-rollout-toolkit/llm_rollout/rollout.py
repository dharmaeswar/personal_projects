"""Rollout loop runtime: drive a model step function through tool calls.

The caller supplies `step_fn(session) -> str` (the model's next
assistant message) and a dict of tools. The loop parses tool calls,
executes them, appends tool results, compacts the session when over
budget, and stops on a final answer, an error, or max steps. The full
transcript is returned for inspection and grading.
"""
from . import render
from .session import Session


class RolloutError(Exception):
    pass


def run_rollout(session: Session, step_fn, tools: dict,
                max_steps: int = 10) -> dict:
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    transcript = list(session.messages)
    final_answer = None
    steps = 0
    for _ in range(max_steps):
        steps += 1
        assistant_text = step_fn(session)
        session.add("assistant", assistant_text)
        transcript.append({"role": "assistant", "content": assistant_text})
        calls = render.parse_tool_calls(assistant_text)
        if not calls:
            final_answer = assistant_text
            break
        for call in calls:
            tool = tools.get(call["name"])
            if tool is None:
                result = f"error: unknown tool '{call['name']}'"
            else:
                try:
                    result = str(tool(**call["arguments"]))
                except Exception as exc:  # noqa: BLE001 - surface tool errors in transcript
                    result = f"error: {exc}"
            session.add("tool", result, tool_name=call["name"])
            transcript.append(
                {"role": "tool", "content": result, "tool_name": call["name"]})
        if session.over_budget():
            session.compact()
    else:
        raise RolloutError(f"no final answer within {max_steps} steps")
    return {
        "steps": steps,
        "final_answer": final_answer,
        "transcript": transcript,
        "tokens": session.token_count(),
    }
