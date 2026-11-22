"""Chat-template rendering and tool-call parsing.

Renders a list of messages (system / user / assistant / tool) into a
single prompt string using a small ChatML-style template, and parses
tool calls out of assistant text. Deterministic and dependency-free.
"""
import json
import re

TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL
)

VALID_ROLES = ("system", "user", "assistant", "tool")


def render_chat(messages: list[dict], template: str = "chatml") -> str:
    """Render messages to a prompt. Each message is {"role": ..., "content": ...}.
    Tool messages carry {"role": "tool", "content": ..., "tool_name": ...}."""
    if template != "chatml":
        raise ValueError(f"unknown template '{template}'")
    out = []
    for msg in messages:
        role = msg.get("role")
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role '{role}'")
        content = msg.get("content", "")
        if role == "tool":
            out.append(
                f"<|im_start|>tool name={msg.get('tool_name', 'tool')}\n{content}<|im_end|>"
            )
        else:
            out.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    out.append("<|im_start|>assistant\n")
    return "\n".join(out)


def parse_tool_calls(text: str) -> list[dict]:
    """Extract <tool_call>{...json...}</tool_call> blocks. Each JSON object
    must have "name" and "arguments". Malformed blocks are skipped, and
    the skip is reported via the returned "errors" list."""
    calls, errors = [], []
    for match in TOOL_CALL_RE.finditer(text):
        try:
            obj = json.loads(match.group(1))
        except json.JSONDecodeError:
            errors.append(match.group(1)[:80])
            continue
        if not isinstance(obj, dict) or "name" not in obj:
            errors.append(match.group(1)[:80])
            continue
        calls.append({"name": obj["name"], "arguments": obj.get("arguments", {})})
    return calls


def format_tool_call(name: str, arguments: dict) -> str:
    return "<tool_call>" + json.dumps({"name": name, "arguments": arguments}) + "</tool_call>"
