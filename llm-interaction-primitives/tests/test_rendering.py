"""Tests for chat-template rendering."""

import pytest

from interaction_lib import Message, render_chat


def test_chatml_rendering():
    msgs = [Message("system", "Be helpful."), Message("user", "Hi")]
    rendered = render_chat(msgs, template="chatml")
    assert rendered == "<|im_start|>system\nBe helpful.<|im_end|>\n<|im_start|>user\nHi<|im_end|>\n"


def test_generation_prompt_appends_open_assistant_turn():
    msgs = [Message("user", "Hi")]
    rendered = render_chat(msgs, template="chatml", add_generation_prompt=True)
    assert rendered.endswith("<|im_start|>assistant\n")


def test_plain_template():
    msgs = [Message("user", "Hi")]
    assert render_chat(msgs, template="plain") == "User: Hi\n"


def test_empty_transcript_rejected():
    with pytest.raises(ValueError):
        render_chat([])


def test_unknown_template_rejected():
    with pytest.raises(ValueError):
        render_chat([Message("user", "Hi")], template="jinja")


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        Message("admin", "Hi")


def test_empty_content_rejected():
    with pytest.raises(ValueError):
        Message("user", "")
