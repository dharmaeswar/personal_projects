"""Chat-template rendering: typed messages -> prompt text for sampling.

A renderer is the first layer of the model-interaction stack: it turns a
structured conversation into the exact string a model samples from. Two
templates ship here — a ChatML-style template with explicit turn markers
and a plain ``Role: content`` template — and both reject unknown roles and
empty transcripts instead of silently producing a wrong prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_ROLES = ("system", "user", "assistant", "tool")

CHATML_START = "<|im_start|>"
CHATML_END = "<|im_end|>"


@dataclass(frozen=True)
class Message:
    """One turn of a conversation. ``role`` is one of VALID_ROLES."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"unknown role {self.role!r}; expected one of {VALID_ROLES}")
        if not self.content:
            raise ValueError("message content must not be empty")


def _render_chatml(messages: list[Message], add_generation_prompt: bool) -> str:
    parts: list[str] = []
    for msg in messages:
        parts.append(f"{CHATML_START}{msg.role}\n{msg.content}{CHATML_END}\n")
    if add_generation_prompt:
        parts.append(f"{CHATML_START}assistant\n")
    return "".join(parts)


def _render_plain(messages: list[Message], add_generation_prompt: bool) -> str:
    parts: list[str] = []
    for msg in messages:
        parts.append(f"{msg.role.capitalize()}: {msg.content}\n")
    if add_generation_prompt:
        parts.append("Assistant: ")
    return "".join(parts)


TEMPLATES = {"chatml": _render_chatml, "plain": _render_plain}


def render_chat(
    messages: list[Message],
    template: str = "chatml",
    add_generation_prompt: bool = False,
) -> str:
    """Render ``messages`` to prompt text with the named chat template.

    Raises ValueError for an empty transcript or an unknown template name.
    With ``add_generation_prompt`` the result ends with an open assistant
    turn, ready for sampling.
    """
    if not messages:
        raise ValueError("cannot render an empty transcript")
    renderer = TEMPLATES.get(template)
    if renderer is None:
        raise ValueError(f"unknown template {template!r}; expected one of {sorted(TEMPLATES)}")
    return renderer(messages, add_generation_prompt)
