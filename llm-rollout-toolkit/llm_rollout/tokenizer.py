"""A tiny deterministic tokenizer (whitespace + punctuation split).

Used for token budgets, context compaction and token-level parity tests.
It is NOT a BPE tokenizer and makes no claim to match any production
tokenizer; it exists so the library's budgeting and parity logic can be
tested exactly.
"""
import re

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def encode(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def decode(tokens: list[str]) -> str:
    out = ""
    for tok in tokens:
        if not out:
            out = tok
        elif re.match(r"\w", tok):
            out += " " + tok
        else:
            out += tok
    return out


def count(text: str) -> int:
    return len(encode(text))


def parity_check(text: str, other_encode) -> dict:
    """Compare this tokenizer against another encoder on the same text.
    Returns token counts and whether the two agree token-for-token."""
    mine = encode(text)
    other = list(other_encode(text))
    return {
        "text": text,
        "mine": len(mine),
        "other": len(other),
        "parity": mine == other,
        "first_difference": next(
            (i for i, (a, b) in enumerate(zip(mine, other)) if a != b), None
        ),
    }
