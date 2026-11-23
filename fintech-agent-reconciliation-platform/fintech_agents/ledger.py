"""Ledger and reconciliation — the finance data the agents work on.

A ledger entry is one enterprise-system posting (AP/AR/GL); a bank line
is one bank-statement line. The reconciler matches them on amount,
date (within a tolerance window), and reference, and reports breaks:
ledger entries with no bank line, bank lines with no ledger entry, and
amount mismatches on the same reference.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    account: str  # AP | AR | GL
    reference: str
    amount_minor: int  # signed, minor units (cents)
    date: str  # YYYY-MM-DD
    description: str = ""


@dataclass(frozen=True)
class BankLine:
    line_id: str
    reference: str
    amount_minor: int
    date: str
    description: str = ""


@dataclass
class Match:
    entry: LedgerEntry
    line: BankLine
    rule: str  # exact | amount_date | reference_only


@dataclass
class ReconciliationResult:
    matches: list[Match]
    unmatched_ledger: list[LedgerEntry]
    unmatched_bank: list[BankLine]
    mismatches: list[tuple[LedgerEntry, BankLine]]  # same ref, diff amount

    @property
    def match_rate(self) -> float:
        total = len(self.matches) + len(self.unmatched_ledger)
        return len(self.matches) / total if total else 1.0


def _days_between(a: str, b: str) -> int:
    from datetime import date
    da = date.fromisoformat(a)
    db = date.fromisoformat(b)
    return abs((da - db).days)


class Reconciler:
    """Deterministic matcher: exact, then amount+date, then reference."""

    def __init__(self, *, date_tolerance_days: int = 3) -> None:
        self.date_tolerance_days = date_tolerance_days

    def reconcile(self, ledger: list[LedgerEntry],
                  bank: list[BankLine]) -> ReconciliationResult:
        bank_by_ref: dict[str, list[BankLine]] = {}
        for line in bank:
            bank_by_ref.setdefault(line.reference, []).append(line)
        used_lines: set[str] = set()
        matches: list[Match] = []
        mismatches: list[tuple[LedgerEntry, BankLine]] = []
        unmatched_ledger: list[LedgerEntry] = []
        for entry in ledger:
            candidates = [ln for ln in bank_by_ref.get(entry.reference, [])
                          if ln.line_id not in used_lines]
            if not candidates:
                unmatched_ledger.append(entry)
                continue
            exact = [ln for ln in candidates
                     if ln.amount_minor == entry.amount_minor
                     and ln.date == entry.date]
            if exact:
                matches.append(Match(entry, exact[0], "exact"))
                used_lines.add(exact[0].line_id)
                continue
            close = [ln for ln in candidates
                     if ln.amount_minor == entry.amount_minor
                     and _days_between(ln.date, entry.date)
                     <= self.date_tolerance_days]
            if close:
                matches.append(Match(entry, close[0], "amount_date"))
                used_lines.add(close[0].line_id)
                continue
            # Same reference but a different amount: a real mismatch.
            # Same amount with a date outside tolerance is not a match
            # at all — leave both sides unmatched instead.
            wrong_amount = [ln for ln in candidates
                            if ln.amount_minor != entry.amount_minor]
            if wrong_amount:
                mismatches.append((entry, wrong_amount[0]))
                used_lines.add(wrong_amount[0].line_id)
                continue
            unmatched_ledger.append(entry)
        unmatched_bank = [ln for ln in bank if ln.line_id not in used_lines]
        return ReconciliationResult(matches, unmatched_ledger,
                                    unmatched_bank, mismatches)


def variance(actual_minor: int, budget_minor: int) -> dict:
    """Variance analysis: absolute and percentage vs budget."""
    diff = actual_minor - budget_minor
    pct = (diff / budget_minor * 100) if budget_minor else 0.0
    return {"actual_minor": actual_minor, "budget_minor": budget_minor,
            "variance_minor": diff, "variance_pct": round(pct, 2)}
