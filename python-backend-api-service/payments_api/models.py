"""Installment-loan backend service: core domain logic.

Pure Python, no external dependencies. A loan is created from a checkout
request (principal, APR, term in months, merchant, customer id). The service
computes a fixed monthly installment schedule, accepts payments against it,
and tracks status. All money is handled in integer cents to avoid float
rounding errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class ValidationError(ValueError):
    """Raised when a request fails input validation."""


LOAN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_PRINCIPAL_CENTS = 100_000_00  # $100,000
MIN_PRINCIPAL_CENTS = 100  # $1.00
MAX_APR_BPS = 3600  # 36.00%
MIN_TERM_MONTHS = 3
MAX_TERM_MONTHS = 60


def validate_checkout(payload: dict) -> dict:
    """Validate a checkout payload. Returns a cleaned dict or raises."""
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    principal = payload.get("principal_cents")
    apr_bps = payload.get("apr_bps")
    term = payload.get("term_months")
    merchant_id = payload.get("merchant_id")
    customer_id = payload.get("customer_id")

    if not isinstance(principal, int) or isinstance(principal, bool):
        raise ValidationError("principal_cents must be an integer number of cents")
    if principal < MIN_PRINCIPAL_CENTS or principal > MAX_PRINCIPAL_CENTS:
        raise ValidationError("principal_cents must be between 100 and 10000000")
    if not isinstance(apr_bps, int) or isinstance(apr_bps, bool):
        raise ValidationError("apr_bps must be an integer number of basis points")
    if apr_bps < 0 or apr_bps > MAX_APR_BPS:
        raise ValidationError("apr_bps must be between 0 and 3600")
    if not isinstance(term, int) or isinstance(term, bool):
        raise ValidationError("term_months must be an integer")
    if term < MIN_TERM_MONTHS or term > MAX_TERM_MONTHS:
        raise ValidationError("term_months must be between 3 and 60")
    for name, value in (("merchant_id", merchant_id), ("customer_id", customer_id)):
        if not isinstance(value, str) or not LOAN_ID_RE.match(value):
            raise ValidationError(f"{name} must be a non-empty id string")
    return {
        "principal_cents": principal,
        "apr_bps": apr_bps,
        "term_months": term,
        "merchant_id": merchant_id,
        "customer_id": customer_id,
    }


def monthly_payment_cents(principal_cents: int, apr_bps: int, term_months: int) -> int:
    """Fixed monthly installment, rounded to the nearest cent.

    Standard amortization formula. A 0% APR loan splits the principal evenly.
    """
    if apr_bps == 0:
        return -(-principal_cents // term_months)  # ceil division
    monthly_rate = (apr_bps / 10_000) / 12
    factor = (1 + monthly_rate) ** term_months
    payment = principal_cents * monthly_rate * factor / (factor - 1)
    return int(round(payment))


def build_schedule(principal_cents: int, apr_bps: int, term_months: int) -> list[dict]:
    """Monthly amortization schedule. Installments sum to principal + interest.

    The last installment absorbs any rounding remainder so the schedule
    always closes the loan exactly to zero.
    """
    payment = monthly_payment_cents(principal_cents, apr_bps, term_months)
    monthly_rate = (apr_bps / 10_000) / 12
    balance = principal_cents
    schedule = []
    for month in range(1, term_months + 1):
        interest = int(round(balance * monthly_rate))
        if month == term_months:
            principal_part = balance
            installment = principal_part + interest
        else:
            principal_part = payment - interest
            installment = payment
        balance -= principal_part
        schedule.append(
            {
                "month": month,
                "installment_cents": installment,
                "principal_cents": principal_part,
                "interest_cents": interest,
                "remaining_balance_cents": balance,
            }
        )
    return schedule


@dataclass
class Loan:
    id: str
    principal_cents: int
    apr_bps: int
    term_months: int
    merchant_id: str
    customer_id: str
    status: str = "active"
    schedule: list[dict] = field(default_factory=list)
    paid_cents: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "principal_cents": self.principal_cents,
            "apr_bps": self.apr_bps,
            "term_months": self.term_months,
            "merchant_id": self.merchant_id,
            "customer_id": self.customer_id,
            "status": self.status,
            "paid_cents": self.paid_cents,
            "total_due_cents": sum(s["installment_cents"] for s in self.schedule),
        }

    def apply_payment(self, amount_cents: int) -> dict:
        """Apply a payment. Returns the updated loan view."""
        if self.status != "active":
            raise ValidationError(f"loan {self.id} is {self.status}, not active")
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
            raise ValidationError("amount_cents must be an integer number of cents")
        if amount_cents <= 0:
            raise ValidationError("amount_cents must be positive")
        total_due = sum(s["installment_cents"] for s in self.schedule)
        remaining = total_due - self.paid_cents
        if amount_cents > remaining:
            raise ValidationError(
                f"amount_cents exceeds remaining balance of {remaining} cents"
            )
        self.paid_cents += amount_cents
        if self.paid_cents == total_due:
            self.status = "paid_off"
        return self.to_dict()
