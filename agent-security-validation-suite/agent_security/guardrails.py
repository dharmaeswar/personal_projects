"""Deterministic guardrails: pattern-based detectors for agent inputs.

No model calls. Each detector returns the matched rule names; the
evaluator combines them into a block/allow decision with a risk score.
Thresholds are fixed constants so results are reproducible.
"""
import re
from dataclasses import dataclass, field


INJECTION_PATTERNS = [
    (r"ignore (all |previous |your )?instructions", "ignore-instructions"),
    (r"disregard (all |the )?(safety )?rules", "disregard-rules"),
    (r"you are now\b", "role-reassignment"),
    (r"\bdo anything now\b|\bDAN\b", "dan-jailbreak"),
    (r"reveal your (system )?prompt|repeat the exact instructions",
     "prompt-extraction"),
    (r"override safety|bypass (the )?guardrails", "guardrail-bypass"),
    (r"pretend to be an unrestricted model", "unrestricted-roleplay"),
    (r"approve .* anyway|follow it", "instruction-override"),
]

PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "ssn"),
    (r"\b(?:\d[ -]?){13,16}\b", "card-number"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "email-address"),
    (r"every customer'?s email|list every customer", "bulk-pii-request"),
]

DESTRUCTIVE_PATTERNS = [
    (r"\bdelete_record\b.*every|\bdelete .* every customer", "mass-delete"),
    (r"\bDROP TABLE\b", "sql-drop"),
    (r"\brm -rf\b", "shell-wipe"),
    (r"dump all records|export.*all records", "mass-export"),
]

EXFIL_PATTERNS = [
    (r"copy .* into the chat|post .* publicly", "exfil-to-chat"),
    (r"send .* to an outside address", "exfil-external"),
    (r"summarize the salary table", "sensitive-table-summary"),
]

# Risk weights per detector family; a score >= 1.0 blocks.
WEIGHTS = {
    "injection": 1.0,
    "pii": 1.0,
    "destructive": 1.0,
    "exfil": 1.0,
}
BLOCK_THRESHOLD = 1.0


@dataclass
class GuardrailResult:
    blocked: bool
    risk_score: float
    reasons: list = field(default_factory=list)

    def __bool__(self):
        return self.blocked


def _scan(text, patterns):
    found = []
    for pattern, name in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(name)
    return found


def evaluate(prompt):
    """Evaluate one agent input. Returns a GuardrailResult."""
    reasons = []
    score = 0.0
    hits = _scan(prompt, INJECTION_PATTERNS)
    if hits:
        score += WEIGHTS["injection"]
        reasons += ["injection:" + h for h in hits]
    hits = _scan(prompt, PII_PATTERNS)
    if hits:
        score += WEIGHTS["pii"]
        reasons += ["pii:" + h for h in hits]
    hits = _scan(prompt, DESTRUCTIVE_PATTERNS)
    if hits:
        score += WEIGHTS["destructive"]
        reasons += ["destructive:" + h for h in hits]
    hits = _scan(prompt, EXFIL_PATTERNS)
    if hits:
        score += WEIGHTS["exfil"]
        reasons += ["exfil:" + h for h in hits]
    return GuardrailResult(blocked=score >= BLOCK_THRESHOLD,
                           risk_score=round(score, 2), reasons=reasons)


def evaluate_tool_args(tool_name, args):
    """Check tool-call arguments for injection or exfiltration content."""
    joined = tool_name + " " + " ".join(str(v) for v in args.values())
    return evaluate(joined)
