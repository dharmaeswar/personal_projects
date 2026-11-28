"""A small deterministic tokenizer for parity testing.

This is a demo tokenizer, not a production BPE implementation: it splits
text into word, number and single-punctuation tokens with a regex, assigns
token ids in first-seen order (so two fresh tokenizers encode the same
text identically), and reserves fixed ids for special tokens. Its value
here is the encode/decode round trip and the token-level parity check in
``parity.py`` — the same shape of test a libraries team runs against a
reference implementation before a model launch.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z]+|[0-9]+|\n|[^\sA-Za-z0-9]")

SPECIAL_TOKENS = {
    "<|bos|>": 0,
    "<|eos|>": 1,
    "<|im_start|>": 2,
    "<|im_end|>": 3,
}

_OPENERS = set("([{\"'")
_PUNCT = set(".,!?;:)]}")


class SimpleTokenizer:
    """Deterministic word/number/punctuation tokenizer with stable ids."""

    def __init__(self) -> None:
        self._token_to_id: dict[str, int] = dict(SPECIAL_TOKENS)
        self._id_to_token: dict[int, str] = {v: k for k, v in SPECIAL_TOKENS.items()}
        self._next_id = max(SPECIAL_TOKENS.values()) + 1

    def tokenize(self, text: str) -> list[str]:
        """Split text into tokens. Special-token strings stay whole."""
        tokens: list[str] = []
        i = 0
        while i < len(text):
            matched_special = False
            for special in SPECIAL_TOKENS:
                if text.startswith(special, i):
                    tokens.append(special)
                    i += len(special)
                    matched_special = True
                    break
            if matched_special:
                continue
            match = _TOKEN_RE.match(text, i)
            if match is not None:
                tokens.append(match.group(0))
                i = match.end()
            else:
                # Whitespace: skipped, it carries no token.
                i += 1
        return tokens

    def encode(self, text: str) -> list[int]:
        """Encode text to token ids, assigning new ids in first-seen order."""
        ids: list[int] = []
        for token in self.tokenize(text):
            token_id = self._token_to_id.get(token)
            if token_id is None:
                token_id = self._next_id
                self._token_to_id[token] = token_id
                self._id_to_token[token_id] = token
                self._next_id += 1
            ids.append(token_id)
        return ids

    def decode(self, ids: list[int]) -> str:
        """Decode token ids back to text, re-inserting spaces between words.

        Spacing rule: a space goes between two tokens except before closing
        punctuation, after an opening bracket/quote, and around special
        tokens and newlines. Operators such as ``+`` keep spaces on both
        sides; apostrophes and brackets do not split a word.
        """
        tokens = [self._id_to_token[token_id] for token_id in ids]
        out = ""
        prev_special = False
        for token in tokens:
            if token in SPECIAL_TOKENS:
                out += token
                prev_special = True
                continue
            if token == "\n":
                out += "\n"
                prev_special = False
                continue
            if not out or prev_special or out.endswith("\n") or out[-1] in _OPENERS or token in _PUNCT or token in _OPENERS:
                out += token
            else:
                out += " " + token
            prev_special = False
        return out

    @property
    def vocab_size(self) -> int:
        return len(self._token_to_id)
