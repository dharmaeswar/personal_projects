"""Lexer for the tiny GPU kernel DSL.

Example input:

    kernel saxpy(a: f32[N], b: f32[N], s: f32) -> c: f32[N] {
        c[i] = a[i] * s + b[i];
    }

Tokens: identifiers, numbers, keywords (kernel, let, for, in, f32),
symbols (->, .., :, ,, ;, =, (, ), {, }, [, ], +, -, *, /, %).
"""

import re

KEYWORDS = {"kernel", "let", "for", "in", "f32"}

TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
    | (?P<num>\d+\.\d+|\d+)
    | (?P<arrow>->)
    | (?P<range>\.\.)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<sym>[+\-*/%:;,=\(\)\{\}\[\]])
    """,
    re.VERBOSE,
)


class Token:
    def __init__(self, kind, value, pos):
        self.kind = kind  # 'num' | 'ident' | 'keyword' | 'sym'
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r})"


class LexError(Exception):
    pass


def tokenize(source):
    """Turn DSL source text into a list of Tokens (no trailing EOF token)."""
    tokens = []
    for m in TOKEN_RE.finditer(source):
        if m.lastgroup == "ws":
            continue
        kind = m.lastgroup
        text = m.group()
        if kind in ("arrow", "range"):
            kind = "sym"
        if kind == "ident" and text in KEYWORDS:
            kind = "keyword"
        if kind == "num":
            value = float(text) if "." in text else int(text)
        else:
            value = text
        tokens.append(Token(kind, value, m.start()))
    # Anything left unmatched is an error: find the first gap.
    covered = set()
    for m in TOKEN_RE.finditer(source):
        covered.update(range(m.start(), m.end()))
    for i, ch in enumerate(source):
        if i not in covered:
            raise LexError(f"unexpected character {ch!r} at offset {i}")
    return tokens
