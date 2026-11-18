"""Reporting workflow: scheduled run, exception queue, sign-off checklist.

This models the control steps around a risk report — run, review
exceptions, sign off — in plain Python. It is not a scheduler and not
a production control system.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SIGNOFF_ITEMS = [
    "Limit breaches reviewed and explained",
    "Liquidity stress results reviewed",
    "Exception queue cleared or escalated",
    "Report figures reconciled (Python vs SQL)",
    "Report distributed to stakeholders",
]


@dataclass
class ExceptionQueue:
    """Breaches and data exceptions, most severe first."""

    items: list[dict] = field(default_factory=list)

    def add_breaches(self, limit_results) -> None:
        for r in limit_results:
            if r.status == "BREACH":
                self.items.append({
                    "trade_id": "",
                    "desk": r.desk,
                    "risk_type": r.risk_type,
                    "reason": (
                        f"limit breach: utilisation {r.utilisation * 100:.1f}% "
                        f"(exposure {r.exposure_usd:,.2f} vs limit "
                        f"{r.limit_usd:,.2f})"
                    ),
                    "severity": "HIGH",
                })

    def add_data_exceptions(self, exceptions: list[dict]) -> None:
        self.items.extend(exceptions)

    def sorted(self) -> list[dict]:
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        return sorted(self.items,
                      key=lambda e: (order.get(e["severity"], 3),
                                     e["desk"], e["risk_type"]))

    def open_count(self) -> int:
        return len([e for e in self.items if e.get("status", "OPEN") == "OPEN"])


@dataclass
class SignoffChecklist:
    items: list[dict] = field(default_factory=list)

    @classmethod
    def fresh(cls) -> "SignoffChecklist":
        return cls([{"item": name, "status": "PENDING", "signed_by": ""}
                    for name in SIGNOFF_ITEMS])

    def sign(self, item: str, signed_by: str) -> None:
        for row in self.items:
            if row["item"] == item:
                row["status"] = "SIGNED"
                row["signed_by"] = signed_by
                return
        raise ValueError(f"unknown checklist item: {item}")

    def all_signed(self) -> bool:
        return all(row["status"] == "SIGNED" for row in self.items)

    def pending(self) -> list[str]:
        return [row["item"] for row in self.items
                if row["status"] != "SIGNED"]


def scheduled_run_summary(as_of_date: str, n_positions: int,
                          n_limits: int, n_breaches: int,
                          n_exceptions: int) -> str:
    """One-line summary a scheduled run would log."""
    return (
        f"[{as_of_date}] scheduled risk-report run: {n_positions} positions, "
        f"{n_limits} limits checked, {n_breaches} breach(es), "
        f"{n_exceptions} exception(s) queued"
    )
