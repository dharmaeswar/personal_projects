"""Token-level parity checks against a reference implementation.

Before a model launch, a libraries team checks that its tokenizer agrees
with the reference implementation token for token. ``check_token_parity``
encodes the same text with this library's tokenizer and with a caller
supplied reference encoder, and reports the first mismatch index so a
failure points at the exact token that diverged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .tokenizer import SimpleTokenizer


@dataclass(frozen=True)
class ParityResult:
    """One parity check: whether the token streams matched, and where not."""

    matched: bool
    first_mismatch: int | None
    ours: list[str]
    reference: list[str]


def check_token_parity(
    text: str,
    reference_encode: Callable[[str], list[str]],
    tokenizer: SimpleTokenizer | None = None,
) -> ParityResult:
    """Compare this tokenizer's tokens with a reference encoder's, token by token."""
    tokenizer = tokenizer or SimpleTokenizer()
    ours = tokenizer.tokenize(text)
    reference = reference_encode(text)
    for index, (ours_token, ref_token) in enumerate(zip(ours, reference)):
        if ours_token != ref_token:
            return ParityResult(False, index, ours, reference)
    if len(ours) != len(reference):
        return ParityResult(False, min(len(ours), len(reference)), ours, reference)
    return ParityResult(True, None, ours, reference)
