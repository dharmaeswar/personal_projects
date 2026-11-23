"""Autonomous security automation — detect, analyze, respond at scale.

Models the NextGen Security Automation work in the Amazon Autonomous AI
Security posting: AI/ML-driven systems that automate detection, analysis,
and response across proactive, offensive, and defensive security.

Pipeline: normalized threat signals -> detectors (each a small, testable
rule over a signal window) -> findings with severity and confidence ->
a responder that executes low-risk containment automatically and holds
high-impact actions for human approval. Responses are idempotent per
finding id, so a retried event never double-revokes or double-quarantines.

All signals are synthetic and deterministic. Nothing here claims
production use or real threat intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signal:
    signal_id: str
    timestamp: int  # epoch seconds
    source: str  # host / IP / principal the signal came from
    kind: str  # auth.failure | egress.bytes | role.assume | indicator.hit ...
    severity: int  # 1 (low) .. 5 (critical), as reported by the producer
    indicators: dict = field(default_factory=dict)


@dataclass
class Finding:
    finding_id: str
    detector: str
    severity: int  # 1..5, raised by the detector when warranted
    confidence: float  # 0.0..1.0
    subject: str
    evidence: str


@dataclass
class ResponseAction:
    action_id: str
    finding_id: str
    action: str  # revoke_session | quarantine_host | block_indicator | ...
    status: str  # executed | pending_approval | skipped_duplicate


# ---------------------------------------------------------------- detectors

class BruteForceDetector:
    """5+ failed auth attempts from one source inside 60 seconds."""

    name = "brute_force"
    threshold = 5
    window_s = 60

    def detect(self, signals: list[Signal]) -> list[Finding]:
        failures = [s for s in signals if s.kind == "auth.failure"]
        by_source: dict[str, list[Signal]] = {}
        for s in failures:
            by_source.setdefault(s.source, []).append(s)
        findings = []
        for source, rows in by_source.items():
            rows.sort(key=lambda s: s.timestamp)
            for i, start in enumerate(rows):
                window = [r for r in rows[i:]
                          if r.timestamp - start.timestamp <= self.window_s]
                if len(window) >= self.threshold:
                    findings.append(Finding(
                        finding_id=f"bf-{source}-{start.timestamp}",
                        detector=self.name, severity=4, confidence=0.9,
                        subject=source,
                        evidence=f"{len(window)} failed logins in "
                                 f"{self.window_s}s from {source}"))
                    break
        return findings


class EgressAnomalyDetector:
    """Egress bytes above a fixed baseline for one source in an hour."""

    name = "egress_anomaly"

    def __init__(self, baseline_bytes: int = 1_000_000,
                 multiplier: float = 10.0) -> None:
        self.baseline_bytes = baseline_bytes
        self.multiplier = multiplier

    def detect(self, signals: list[Signal]) -> list[Finding]:
        totals: dict[str, int] = {}
        for s in signals:
            if s.kind == "egress.bytes":
                totals[s.source] = totals.get(s.source, 0) + \
                    int(s.indicators.get("bytes", 0))
        findings = []
        for source, total in totals.items():
            if total > self.baseline_bytes * self.multiplier:
                findings.append(Finding(
                    finding_id=f"eg-{source}",
                    detector=self.name, severity=3, confidence=0.8,
                    subject=source,
                    evidence=f"{total} egress bytes vs "
                             f"{self.baseline_bytes} baseline"))
        return findings


class PrivilegeEscalationDetector:
    """A read-only role assume followed by an admin assume, same subject."""

    name = "privilege_escalation"

    def detect(self, signals: list[Signal]) -> list[Finding]:
        assumes = [s for s in signals if s.kind == "role.assume"]
        findings = []
        for i, first in enumerate(assumes):
            if first.indicators.get("role") != "read-only":
                continue
            for second in assumes[i + 1:]:
                if (second.indicators.get("subject") ==
                        first.indicators.get("subject")
                        and second.indicators.get("role") == "admin"
                        and 0 < second.timestamp - first.timestamp <= 600):
                    findings.append(Finding(
                        finding_id=f"pe-{first.indicators.get('subject')}"
                                   f"-{first.timestamp}",
                        detector=self.name, severity=5, confidence=0.95,
                        subject=str(first.indicators.get("subject")),
                        evidence="read-only role assumed, then admin role "
                                 "within 10 minutes"))
                    break
        return findings


class IndicatorMatchDetector:
    """A signal carrying an indicator from the known-bad set."""

    name = "indicator_match"

    def __init__(self, known_bad: set[str] | None = None) -> None:
        self.known_bad = known_bad or set()

    def detect(self, signals: list[Signal]) -> list[Finding]:
        findings = []
        for s in signals:
            hits = set(s.indicators.get("indicators", [])) & self.known_bad
            if hits:
                findings.append(Finding(
                    finding_id=f"im-{s.signal_id}",
                    detector=self.name, severity=4, confidence=0.95,
                    subject=s.source,
                    evidence=f"known-bad indicator(s): {sorted(hits)}"))
        return findings


DETECTORS = [BruteForceDetector, EgressAnomalyDetector,
             PrivilegeEscalationDetector, IndicatorMatchDetector]


def detect_all(signals: list[Signal],
               known_bad: set[str] | None = None) -> list[Finding]:
    """Run every detector; findings are sorted by severity, then id."""
    out: list[Finding] = []
    out += BruteForceDetector().detect(signals)
    out += EgressAnomalyDetector().detect(signals)
    out += PrivilegeEscalationDetector().detect(signals)
    out += IndicatorMatchDetector(known_bad).detect(signals)
    out.sort(key=lambda f: (-f.severity, f.finding_id))
    return out


# ---------------------------------------------------------------- responder

# Actions the responder may execute without a human in the loop.
AUTO_ACTIONS = {
    1: ["log_finding"],
    2: ["log_finding", "notify_oncall"],
    3: ["log_finding", "notify_oncall", "revoke_session"],
    4: ["log_finding", "notify_oncall", "revoke_session",
        "quarantine_host", "block_indicator"],
    5: ["log_finding", "notify_oncall", "revoke_session",
        "quarantine_host", "block_indicator"],
}
# Severity 5 also needs a human-approved containment step.
APPROVAL_ACTIONS = {5: ["disable_account", "isolate_network"]}


class Responder:
    """Executes containment for a finding, idempotently per finding id."""

    def __init__(self) -> None:
        self._handled: dict[str, list[ResponseAction]] = {}

    def respond(self, finding: Finding) -> list[ResponseAction]:
        if finding.finding_id in self._handled:
            return [ResponseAction(
                action_id=f"{a.action_id}-dup", finding_id=finding.finding_id,
                action=a.action, status="skipped_duplicate")
                for a in self._handled[finding.finding_id]]
        actions = [ResponseAction(
            action_id=f"{finding.finding_id}-{name}",
            finding_id=finding.finding_id, action=name, status="executed")
            for name in AUTO_ACTIONS.get(finding.severity, ["log_finding"])]
        actions += [ResponseAction(
            action_id=f"{finding.finding_id}-{name}",
            finding_id=finding.finding_id, action=name,
            status="pending_approval")
            for name in APPROVAL_ACTIONS.get(finding.severity, [])]
        self._handled[finding.finding_id] = actions
        return actions


# ---------------------------------------------------------------- scenarios

def _sig(sid: str, ts: int, source: str, kind: str, sev: int = 2,
         **ind) -> Signal:
    return Signal(sid, ts, source, kind, sev, ind)


def run_autonomous_suite() -> list[dict]:
    """Deterministic detection + response scenarios with expected outcomes.

    Each row: scenario, expected finding detector (or None), expected
    response statuses, and whether the run matched.
    """
    scenarios = [
        {
            "name": "brute force burst detected and session revoked",
            "signals": [_sig(f"a{i}", 1000 + i * 10, "10.0.0.7",
                             "auth.failure", 3) for i in range(6)],
            "expect_detector": "brute_force",
            "expect_actions": {"revoke_session": "executed"},
        },
        {
            "name": "four failures stay below the brute-force threshold",
            "signals": [_sig(f"b{i}", 1000 + i * 10, "10.0.0.8",
                             "auth.failure", 2) for i in range(4)],
            "expect_detector": None,
            "expect_actions": {},
        },
        {
            "name": "egress spike detected above baseline",
            "signals": [_sig("e1", 2000, "host-9", "egress.bytes", 3,
                             bytes=12_000_000)],
            "expect_detector": "egress_anomaly",
            "expect_actions": {"revoke_session": "executed"},
        },
        {
            "name": "normal egress stays below the anomaly threshold",
            "signals": [_sig("e2", 2000, "host-9", "egress.bytes", 1,
                             bytes=500_000)],
            "expect_detector": None,
            "expect_actions": {},
        },
        {
            "name": "read-only then admin assume is privilege escalation",
            "signals": [
                _sig("p1", 3000, "console", "role.assume", 2,
                     subject="alice", role="read-only"),
                _sig("p2", 3300, "console", "role.assume", 4,
                     subject="alice", role="admin"),
            ],
            "expect_detector": "privilege_escalation",
            "expect_actions": {"disable_account": "pending_approval"},
        },
        {
            "name": "admin assume alone is not escalation",
            "signals": [_sig("p3", 3000, "console", "role.assume", 2,
                             subject="bob", role="admin")],
            "expect_detector": None,
            "expect_actions": {},
        },
        {
            "name": "known-bad indicator match quarantines the host",
            "signals": [_sig("i1", 4000, "host-4", "indicator.hit", 4,
                             indicators=["bad-domain.example",
                                         "clean.example"])],
            "expect_detector": "indicator_match",
            "expect_actions": {"quarantine_host": "executed"},
        },
        {
            "name": "unknown indicator does not fire",
            "signals": [_sig("i2", 4000, "host-4", "indicator.hit", 1,
                             indicators=["clean.example"])],
            "expect_detector": None,
            "expect_actions": {},
        },
    ]
    known_bad = {"bad-domain.example", "bad-ip-1.2.3.4"}
    rows = []
    for sc in scenarios:
        findings = detect_all(sc["signals"], known_bad)
        got = findings[0].detector if findings else None
        actions: dict[str, str] = {}
        responder = Responder()
        for f in findings:
            for a in responder.respond(f):
                actions[a.action] = a.status
        expected = sc["expect_actions"]
        passed = got == sc["expect_detector"] and all(
            actions.get(k) == v for k, v in expected.items())
        rows.append({"scenario": sc["name"],
                     "expected_detector": sc["expect_detector"],
                     "got_detector": got,
                     "actions": actions,
                     "passed": passed})
    return rows
