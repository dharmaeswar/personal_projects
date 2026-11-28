"""Public API for llm-interaction-primitives.

One typed entry point per layer of the model-interaction stack, in the
order a request flows through them: render -> tokenize -> sample (rollout)
-> parse tool calls -> grade -> version.
"""

from .graders import GradeResult, grade_exact_match, grade_json_validity, grade_tool_call
from .parity import ParityResult, check_token_parity
from .rendering import Message, render_chat
from .rollout import RolloutResult, run_rollout
from .session import Session
from .tokenizer import SimpleTokenizer
from .tool_calls import ToolCall, ToolSpec, parse_tool_calls, validate_tool_call
from .versioning import bump_version, changelog_entry, deprecated, parse_version

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "Message",
    "render_chat",
    "SimpleTokenizer",
    "ToolCall",
    "ToolSpec",
    "parse_tool_calls",
    "validate_tool_call",
    "Session",
    "RolloutResult",
    "run_rollout",
    "GradeResult",
    "grade_exact_match",
    "grade_json_validity",
    "grade_tool_call",
    "ParityResult",
    "check_token_parity",
    "bump_version",
    "changelog_entry",
    "deprecated",
    "parse_version",
]
