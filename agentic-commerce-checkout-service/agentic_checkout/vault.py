"""Tokenization: replace a payment credential with an opaque reference.

A card number is never stored or logged in the clear.  `tokenize` returns
an opaque `tok_...` reference derived with HMAC, and keeps only the last
four digits and the brand in memory.  `lookup` returns that masked record
— never the full number — and only for a token the vault issued.  All card
numbers in tests and demos are synthetic fixtures, never real credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass


class VaultError(ValueError):
    """Raised for an unknown token or an invalid credential."""


@dataclass(frozen=True)
class MaskedCredential:
    token: str
    brand: str
    last4: str


_CARD_RE = re.compile(r"^\d{13,19}$")


def _brand(number: str) -> str:
    if number.startswith("4"):
        return "visa"
    if number.startswith(("51", "52", "53", "54", "55")):
        return "mastercard"
    if number.startswith(("34", "37")):
        return "amex"
    return "unknown"


class TokenVault:
    """In-memory token vault.  Demo only — a real vault is a PCI service."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self._records: dict[str, MaskedCredential] = {}

    def tokenize(self, card_number: str) -> MaskedCredential:
        """Store a credential and return its opaque token + masked record."""
        digits = re.sub(r"\D", "", card_number)
        if not _CARD_RE.match(digits):
            raise VaultError("card number must be 13-19 digits")
        if not _luhn_ok(digits):
            raise VaultError("card number fails the Luhn check")
        digest = hmac.new(self._secret, digits.encode(), hashlib.sha256).hexdigest()
        token = f"tok_{digest[:24]}"
        record = MaskedCredential(token=token, brand=_brand(digits), last4=digits[-4:])
        self._records[token] = record
        return record

    def lookup(self, token: str) -> MaskedCredential:
        """Return the masked record for a token; the PAN is never returned."""
        try:
            return self._records[token]
        except KeyError:
            raise VaultError(f"unknown payment token {token!r}") from None


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
