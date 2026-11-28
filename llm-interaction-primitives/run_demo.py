"""End-to-end demo: render, tokenize, roll out, parse, grade, version.

Runs the full stack on synthetic data — a chat about adding two numbers,
a fake sampler, one tool call — and prints each layer's result. No model
calls, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from interaction_lib import (  # noqa: E402
    Message,
    Session,
    SimpleTokenizer,
    ToolSpec,
    check_token_parity,
    grade_exact_match,
    grade_tool_call,
    parse_tool_calls,
    render_chat,
    run_rollout,
    validate_tool_call,
)


def _fake_sampler(messages: list[Message]) -> str:
    last = messages[-1].content
    if "2 + 2" in last:
        return "The answer is 4. ```json\n{\"name\": \"add\", \"arguments\": {\"a\": 2, \"b\": 2}}\n```"
    return "Done. <|eos|>"


def _fake_executor(call):  # type: ignore[no-untyped-def]
    if call.name == "add":
        return str(call.arguments["a"] + call.arguments["b"])
    return "unknown tool"


def main() -> int:
    tok = SimpleTokenizer()
    messages = [
        Message("system", "You are a helpful assistant."),
        Message("user", "What is 2 + 2?"),
    ]
    prompt = render_chat(messages, template="chatml", add_generation_prompt=True)
    print("--- rendered prompt ---")
    print(prompt)
    ids = tok.encode(prompt)
    print(f"tokens: {len(ids)}  round-trip ok: {tok.decode(ids) == prompt}")

    parity = check_token_parity("What is 2 + 2?", lambda text: tok.tokenize(text))
    print(f"parity vs reference: matched={parity.matched}")

    session = Session(messages=list(messages), tokenizer=tok)
    result = run_rollout(session, _fake_sampler, executor=_fake_executor, max_turns=4)
    print(f"rollout: {result.turns} turns, stopped={result.stopped_reason}, "
          f"tokens={result.total_tokens}, tool calls={len(result.tool_calls)}")

    specs = {"add": ToolSpec("add", parameters={"a": "integer", "b": "integer"},
                             required=("a", "b"))}
    for call in result.tool_calls:
        errors = validate_tool_call(call, specs)
        print(f"tool call {call.name} {call.arguments}: "
              f"{'valid' if not errors else '; '.join(errors)}")
        grade = grade_tool_call(call, "add", {"a": 2, "b": 2})
        print(f"tool-call grade: {grade.score} ({grade.reason})")

    print(f"exact-match grade: {grade_exact_match(' 4 ', '4').score}")
    print(f"parsed calls from assistant reply: {len(parse_tool_calls(result.transcript[2].content))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
