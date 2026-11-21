"""Trusted data vending: scoped, audited access to partner data products.

A data product is a partner dataset (campaign performance, audience
segments, creative assets) with an owner, a schema, and the scopes that
gate it. A consumer (an application or an AI agent) holds an access token
with a set of granted scopes. Vending enforces three rules:

1. The token must carry every scope the data product requires.
2. Sensitive columns are masked unless the token also holds the
   ``sensitive:read`` scope.
3. Every access — granted or denied — is written to an append-only audit
   log with who asked, what they asked for, and why the decision was made.

Tokens expire; an expired token vends nothing. Nothing here touches real
partner data: all rows are synthetic fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SENSITIVE_SCOPE = "sensitive:read"


@dataclass
class DataProduct:
    """One vendable partner dataset."""

    product_id: str
    name: str
    owner: str
    required_scopes: list
    columns: list
    sensitive_columns: list
    rows: list = field(default_factory=list)

    def validate(self) -> list:
        problems = []
        if not self.product_id:
            problems.append("product_id must not be empty")
        if not self.required_scopes:
            problems.append(f"product {self.product_id!r} needs required scopes")
        if not self.columns:
            problems.append(f"product {self.product_id!r} needs columns")
        for col in self.sensitive_columns:
            if col not in self.columns:
                problems.append(
                    f"product {self.product_id!r} sensitive column {col!r} "
                    "is not in columns"
                )
        return problems


@dataclass
class Token:
    """An access token held by an application or agent."""

    token_id: str
    holder: str
    scopes: list
    expires: str  # ISO date

    def expired(self, today: str = "2026-11-21") -> bool:
        return self.expires < today


@dataclass
class AccessRecord:
    """One audit-log entry for a vending decision."""

    token_id: str
    holder: str
    product_id: str
    granted: bool
    reason: str


class DataVending:
    """Registry of data products plus scoped, audited vending."""

    def __init__(self) -> None:
        self._products: dict[str, DataProduct] = {}
        self.audit_log: list[AccessRecord] = []

    def register(self, product: DataProduct) -> None:
        problems = product.validate()
        if problems:
            raise ValueError("; ".join(problems))
        if product.product_id in self._products:
            raise ValueError(f"product {product.product_id!r} already registered")
        self._products[product.product_id] = product

    def get(self, product_id: str) -> DataProduct | None:
        return self._products.get(product_id)

    def vend(self, token: Token, product_id: str, today: str = "2026-11-21") -> dict:
        """Return rows for a product if the token is allowed; else deny + audit."""
        product = self._products.get(product_id)
        if product is None:
            record = AccessRecord(token.token_id, token.holder, product_id,
                                  False, "unknown product")
            self.audit_log.append(record)
            return {"granted": False, "reason": "unknown product", "rows": []}
        if token.expired(today):
            record = AccessRecord(token.token_id, token.holder, product_id,
                                  False, "token expired")
            self.audit_log.append(record)
            return {"granted": False, "reason": "token expired", "rows": []}
        missing = [s for s in product.required_scopes if s not in token.scopes]
        if missing:
            record = AccessRecord(token.token_id, token.holder, product_id,
                                  False, f"missing scopes: {missing}")
            self.audit_log.append(record)
            return {"granted": False, "reason": f"missing scopes: {missing}", "rows": []}
        can_see_sensitive = SENSITIVE_SCOPE in token.scopes
        rows = []
        for row in product.rows:
            visible = {
                col: (val if can_see_sensitive or col not in product.sensitive_columns
                      else "***MASKED***")
                for col, val in row.items()
            }
            rows.append(visible)
        self.audit_log.append(AccessRecord(token.token_id, token.holder,
                                           product_id, True, "granted"))
        return {"granted": True, "reason": "granted", "rows": rows}

    def denied_count(self) -> int:
        return sum(1 for r in self.audit_log if not r.granted)
