"""Tests for llm-rollout-toolkit: render, tokenizer, session, graders,
rollout loop, versioning."""
import warnings

import pytest

from llm_rollout import graders, render, rollout, session, tokenizer, versioning


def test_render_chatml_and_invalid_role():
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hi"},
        {"role": "tool", "content": "42", "tool_name": "calculator"},
    ]
    prompt = render.render_chat(messages)
    assert "<|im_start|>system\nBe helpful.<|im_end|>" in prompt
    assert "<|im_start|>tool name=calculator\n42<|im_end|>" in prompt
    assert prompt.endswith("<|im_start|>assistant\n")
    with pytest.raises(ValueError, match="invalid role"):
        render.render_chat([{"role": "robot", "content": "x"}])
    with pytest.raises(ValueError, match="unknown template"):
        render.render_chat(messages, template="llama")


def test_parse_tool_calls_and_errors():
    text = (
        'I will compute this. '
        + render.format_tool_call("calculator", {"expression": "2+2"})
        + ' <tool_call>{not json</tool_call>'
        + ' <tool_call>{"arguments": {}}</tool_call>'
    )
    calls = render.parse_tool_calls(text)
    assert calls == [{"name": "calculator", "arguments": {"expression": "2+2"}}]
    assert render.parse_tool_calls("no calls here") == []


def test_tokenizer_encode_decode_parity():
    text = "Hello, world! How are you?"
    tokens = tokenizer.encode(text)
    assert tokens == ["Hello", ",", "world", "!", "How", "are", "you", "?"]
    assert tokenizer.decode(tokens) == text
    assert tokenizer.count(text) == 8
    parity = tokenizer.parity_check(text, lambda t: tokenizer.encode(t))
    assert parity["parity"] is True and parity["first_difference"] is None
    parity2 = tokenizer.parity_check(text, lambda t: t.split())
    assert parity2["parity"] is False


def test_session_compaction():
    sess = session.Session("System prompt here.", token_budget=12)
    sess.add("user", "one two three four five six")
    sess.add("assistant", "seven eight nine ten eleven twelve")
    sess.add("user", "thirteen fourteen fifteen sixteen")
    assert sess.over_budget()
    report = sess.compact()
    assert report["dropped"] >= 1
    assert not sess.over_budget()
    assert sess.messages[0]["role"] == "system"


def test_session_no_compact_when_inside_budget():
    sess = session.Session("Hi.", token_budget=100)
    sess.add("user", "Hello there.")
    assert sess.compact() == {"dropped": 0, "summary": None}


def test_graders():
    assert graders.exact_match("a", "a")["score"] == 1.0
    assert graders.exact_match("a", "b")["score"] == 0.0
    assert graders.regex_match(r"\d+", "abc 42")["score"] == 1.0
    assert graders.regex_match(r"\d+", "abc")["score"] == 0.0
    assert graders.keyword_coverage(["a", "b", "c"], "a and c")["score"] == pytest.approx(2 / 3)
    assert graders.numeric_close(10.0, 10.05, 0.1)["score"] == 1.0
    assert graders.numeric_close(10.0, 11.0, 0.1)["score"] == 0.0
    combined = graders.combine(
        [{"score": 1.0, "reason": "x"}, {"score": 0.0, "reason": "y"}],
        weights=[3.0, 1.0])
    assert combined["score"] == pytest.approx(0.75)
    with pytest.raises(ValueError):
        graders.combine([])
    with pytest.raises(ValueError):
        graders.keyword_coverage([], "text")


def test_rollout_with_tool_and_final_answer():
    sess = session.Session("Be helpful.", token_budget=500)
    sess.add("user", "What is 3 + 4?")
    calls = {"n": 0}

    def step_fn(s):
        calls["n"] += 1
        if calls["n"] == 1:
            return render.format_tool_call("add", {"a": 3, "b": 4})
        return "The answer is 7."

    result = rollout.run_rollout(
        sess, step_fn, {"add": lambda a, b: a + b}, max_steps=5)
    assert result["steps"] == 2
    assert result["final_answer"] == "The answer is 7."
    tool_msgs = [m for m in result["transcript"] if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[0]["content"] == "7"


def test_rollout_unknown_tool_and_max_steps():
    sess = session.Session("", token_budget=500)
    sess.add("user", "hi")
    calls = {"n": 0}

    def step_fn(s):
        calls["n"] += 1
        if calls["n"] == 1:
            return render.format_tool_call("nope", {})
        return "done without tools."

    result = rollout.run_rollout(sess, step_fn, {}, max_steps=3)
    assert result["final_answer"] == "done without tools."
    tool_msgs = [m for m in result["transcript"] if m["role"] == "tool"]
    assert tool_msgs and "unknown tool 'nope'" in tool_msgs[0]["content"]
    # A step function that always calls tools must hit the step limit.
    sess2 = session.Session("", token_budget=500)
    sess2.add("user", "hi")
    with pytest.raises(rollout.RolloutError, match="no final answer"):
        rollout.run_rollout(
            sess2, lambda s: render.format_tool_call("nope", {}),
            {}, max_steps=2)


def test_versioning():
    assert versioning.parse("1.2.3") == (1, 2, 3)
    assert versioning.bump("1.2.3", "minor") == "1.3.0"
    assert versioning.bump("1.2.3", "major") == "2.0.0"
    assert versioning.bump("1.2.3", "patch") == "1.2.4"
    with pytest.raises(ValueError):
        versioning.parse("1.2")
    with pytest.raises(ValueError):
        versioning.bump("1.2.3", "huge")

    @versioning.deprecated("0.1.0", replacement="new_fn")
    def old_fn():
        return 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert old_fn() == 1
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
