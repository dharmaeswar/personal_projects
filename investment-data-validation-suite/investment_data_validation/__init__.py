"""Shared types and finding/report containers for investment-data validation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    """One documented validation result for one record."""

    check: str
    dataset: str
    record_id: str
    severity: str  # FAIL, WARNING, or INFO
    message: str


@dataclass
class ValidationReport:
    """Pass/fail summary plus every finding for one dataset."""

    dataset: str
    records_checked: int
    checks_run: int
    passed: int
    failed: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARNING")

    @property
    def is_clean(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "records_checked": self.records_checked,
            "checks_run": self.checks_run,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "is_clean": self.is_clean,
            "findings": [
                {
                    "check": f.check,
                    "record_id": f.record_id,
                    "severity": f.severity,
                    "message": f.message,
                }
                for f in self.findings
            ],
        }
