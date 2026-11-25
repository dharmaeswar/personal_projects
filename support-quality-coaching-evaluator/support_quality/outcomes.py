"""Production observability and outcome tracking for Support AI.

The judge scores individual conversations; this module watches the
system that serves them. It answers the questions an engineer on call
for a voice/chat support-AI product asks every morning: what share of
conversations resolved without a human, how many escalated, how slow
is the system getting, is a third-party AI vendor breaching its SLO,
and did the latest release make any of that worse?

It mirrors the Toast Support AI workflow: own a component from design
through production, improve observability, monitoring and outcome
tracking with production data, and keep third-party AI integrations
healthy against API behaviour, latency, reliability and vendor
constraints.

All conversations here are synthetic and seeded, like the rest of this
project. No real customer data, no real vendor, and nothing here
claims a production deployment.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class ConversationOutcome:
    """One finished Support AI conversation."""

    conversation_id: str
    channel: str  # "voice" or "chat"
    resolved_without_human: bool
    escalated: bool
    turns: int
    latency_ms: list = field(default_factory=list)  # per-turn response latency
    vendor: str = "vendor-a"  # third-party AI platform serving the turn
    vendor_errors: int = 0
    csat: float | None = None  # 1-5 post-conversation score, if the customer answered
    cost_usd: float = 0.0


def generate_outcomes(seed=11, n=200):
    """Generate a seeded synthetic set of conversation outcomes.

    Resolution is more likely on chat than voice, latency is higher on
    voice, and one vendor is seeded with a higher error rate so the
    vendor-health check has something real to flag.
    """
    rng = random.Random(seed)
    outcomes = []
    for i in range(n):
        channel = rng.choice(["voice", "chat"])
        vendor = rng.choice(["vendor-a", "vendor-a", "vendor-b"])
        base_latency = 900 if channel == "voice" else 450
        turns = rng.randint(2, 12)
        latency = [max(50, int(rng.gauss(base_latency, 220))) for _ in range(turns)]
        resolved = rng.random() < (0.78 if channel == "chat" else 0.62)
        escalated = (not resolved) or rng.random() < 0.06
        vendor_errors = sum(
            1 for _ in range(turns) if rng.random() < (0.05 if vendor == "vendor-b" else 0.01)
        )
        csat = round(rng.uniform(3.5, 5.0), 1) if resolved and rng.random() < 0.4 else None
        outcomes.append(
            ConversationOutcome(
                conversation_id=f"CONV-{i:04d}",
                channel=channel,
                resolved_without_human=resolved,
                escalated=escalated,
                turns=turns,
                latency_ms=latency,
                vendor=vendor,
                vendor_errors=vendor_errors,
                csat=csat,
                cost_usd=round(turns * 0.012 + vendor_errors * 0.05, 4),
            )
        )
    return outcomes


def _percentile(values, pct):
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[int(rank)])
    return float(ordered[low] * (high - rank) + ordered[high] * (rank - low))


def outcome_summary(outcomes):
    """Summarise a set of conversation outcomes.

    Returns resolution rate, escalation rate, turn and latency
    statistics (mean and p95), vendor error rate, mean CSAT over the
    conversations that answered, and mean cost per conversation.
    Raises ValueError on an empty set.
    """
    outcomes = list(outcomes)
    if not outcomes:
        raise ValueError("no outcomes to summarise")
    n = len(outcomes)
    all_latency = [ms for o in outcomes for ms in o.latency_ms]
    csat_scores = [o.csat for o in outcomes if o.csat is not None]
    return {
        "n_conversations": n,
        "resolution_rate": sum(o.resolved_without_human for o in outcomes) / n,
        "escalation_rate": sum(o.escalated for o in outcomes) / n,
        "mean_turns": sum(o.turns for o in outcomes) / n,
        "mean_latency_ms": sum(all_latency) / len(all_latency),
        "p95_latency_ms": _percentile(all_latency, 95),
        "vendor_error_rate": sum(o.vendor_errors for o in outcomes) / sum(o.turns for o in outcomes),
        "mean_csat": sum(csat_scores) / len(csat_scores) if csat_scores else float("nan"),
        "csat_responses": len(csat_scores),
        "mean_cost_usd": sum(o.cost_usd for o in outcomes) / n,
    }


def detect_regression(baseline, current, max_resolution_drop=0.05, max_p95_rise_pct=25.0):
    """Compare a current summary against a baseline summary.

    Flags a regression when the resolution rate fell by more than
    ``max_resolution_drop`` (in absolute points) or p95 latency rose
    by more than ``max_p95_rise_pct`` percent. Returns a dict with the
    deltas and a list of human-readable findings (empty = no regression).
    """
    resolution_delta = current["resolution_rate"] - baseline["resolution_rate"]
    p95_delta_pct = (
        (current["p95_latency_ms"] - baseline["p95_latency_ms"]) / baseline["p95_latency_ms"] * 100.0
        if baseline["p95_latency_ms"]
        else float("nan")
    )
    findings = []
    if resolution_delta < -max_resolution_drop:
        findings.append(
            f"resolution rate fell {abs(resolution_delta):.1%} "
            f"(baseline {baseline['resolution_rate']:.1%} -> current {current['resolution_rate']:.1%})"
        )
    if p95_delta_pct > max_p95_rise_pct:
        findings.append(
            f"p95 latency rose {p95_delta_pct:.0f}% "
            f"(baseline {baseline['p95_latency_ms']:.0f}ms -> current {current['p95_latency_ms']:.0f}ms)"
        )
    return {
        "resolution_delta": resolution_delta,
        "p95_delta_pct": p95_delta_pct,
        "regressed": bool(findings),
        "findings": findings,
    }


def vendor_health(outcomes, max_error_rate=0.02, max_p95_ms=2000.0):
    """Per-vendor health: error rate, p95 latency, share of turns.

    A vendor is flagged when its error rate exceeds
    ``max_error_rate`` or its p95 latency exceeds ``max_p95_ms`` —
    the point where a fallback or a vendor conversation is due.
    """
    by_vendor = {}
    for outcome in outcomes:
        bucket = by_vendor.setdefault(outcome.vendor, {"turns": 0, "errors": 0, "latency": []})
        bucket["turns"] += outcome.turns
        bucket["errors"] += outcome.vendor_errors
        bucket["latency"].extend(outcome.latency_ms)
    health = {}
    for vendor, bucket in by_vendor.items():
        error_rate = bucket["errors"] / bucket["turns"] if bucket["turns"] else 0.0
        p95 = _percentile(bucket["latency"], 95)
        health[vendor] = {
            "turns": bucket["turns"],
            "error_rate": error_rate,
            "p95_latency_ms": p95,
            "breaching_slo": error_rate > max_error_rate or p95 > max_p95_ms,
        }
    return health


def alert_check(summary, thresholds=None):
    """Turn a summary into on-call alerts.

    Default thresholds: resolution rate below 60%, escalation rate
    above 35%, p95 latency above 2000ms, vendor error rate above 2%.
    Returns a list of alert strings (empty = all clear).
    """
    thresholds = thresholds or {
        "min_resolution_rate": 0.60,
        "max_escalation_rate": 0.35,
        "max_p95_latency_ms": 2000.0,
        "max_vendor_error_rate": 0.02,
    }
    alerts = []
    if summary["resolution_rate"] < thresholds["min_resolution_rate"]:
        alerts.append(f"resolution rate {summary['resolution_rate']:.1%} below {thresholds['min_resolution_rate']:.0%}")
    if summary["escalation_rate"] > thresholds["max_escalation_rate"]:
        alerts.append(f"escalation rate {summary['escalation_rate']:.1%} above {thresholds['max_escalation_rate']:.0%}")
    if summary["p95_latency_ms"] > thresholds["max_p95_latency_ms"]:
        alerts.append(f"p95 latency {summary['p95_latency_ms']:.0f}ms above {thresholds['max_p95_latency_ms']:.0f}ms")
    if summary["vendor_error_rate"] > thresholds["max_vendor_error_rate"]:
        alerts.append(f"vendor error rate {summary['vendor_error_rate']:.2%} above {thresholds['max_vendor_error_rate']:.0%}")
    return alerts
