"""Insurance policy-and-claims module for the backend API service.

Added for the Mercury Insurance — Software Engineer II (Java) application:
the same service patterns as the loan checkout (REST endpoints, strict
validation, integer-cents money math, idempotent writes, event publishing,
caching) applied to an insurance domain — policies, premiums, claims.

Pure Python, standard library only. Two pieces are honest stand-ins for
infrastructure the service is written to plug into later:

- ``EventPublisher`` is an in-memory event log with Kafka-style topics,
  keys and offsets. It is NOT a Kafka broker; a real producer would publish
  the same ``(topic, key, value)`` records to Kafka.
- ``QuoteCache`` is an in-memory TTL cache with the same get/set shape as
  a Redis cache; a real deployment would back it with Redis.

A policy covers one vehicle (``auto``) or one home (``home``). Premiums are
computed in integer cents from the coverage limit, a per-type base rate, a
deductible credit, a state factor and the term length. A claim pays out the
claimed amount minus the deductible, capped at the coverage limit.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from .models import LOAN_ID_RE, ValidationError

POLICY_TYPES = ("auto", "home")
TERM_MONTHS = (6, 12)
STATE_RE = re.compile(r"^[A-Z]{2}$")

MIN_COVERAGE_CENTS = 100_000  # $1,000
MAX_COVERAGE_CENTS = 100_000_000  # $1,000,000
# Base annual premium rate, in basis points of the coverage limit.
BASE_RATE_BPS = {"auto": 500, "home": 320}
# Deductible credit: each basis point of deductible (as a share of coverage)
# cuts the rate by the same amount, capped at a 20% rate reduction.
MAX_DEDUCTIBLE_CREDIT_BPS = 2000
MIN_RATE_BPS = 100  # rate floor: 1% of coverage per year
# State rating factor, in percent (100 = no adjustment).
STATE_FACTOR_PCT = {"CA": 115, "NY": 110, "TX": 105, "FL": 130}
DEFAULT_STATE_FACTOR_PCT = 100
QUOTE_TTL_SECONDS = 300


def validate_policy(payload: dict) -> dict:
    """Validate a policy-creation payload. Returns a cleaned dict or raises."""
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    policy_type = payload.get("policy_type")
    coverage = payload.get("coverage_limit_cents")
    deductible = payload.get("deductible_cents")
    term = payload.get("term_months")
    state = payload.get("state")
    holder_id = payload.get("holder_id")

    if policy_type not in POLICY_TYPES:
        raise ValidationError("policy_type must be 'auto' or 'home'")
    if not isinstance(coverage, int) or isinstance(coverage, bool):
        raise ValidationError("coverage_limit_cents must be an integer number of cents")
    if coverage < MIN_COVERAGE_CENTS or coverage > MAX_COVERAGE_CENTS:
        raise ValidationError("coverage_limit_cents must be between 100000 and 100000000")
    if not isinstance(deductible, int) or isinstance(deductible, bool):
        raise ValidationError("deductible_cents must be an integer number of cents")
    if deductible < 0 or deductible > coverage:
        raise ValidationError("deductible_cents must be between 0 and the coverage limit")
    if term not in TERM_MONTHS:
        raise ValidationError("term_months must be 6 or 12")
    if not isinstance(state, str) or not STATE_RE.match(state):
        raise ValidationError("state must be a two-letter uppercase code")
    if not isinstance(holder_id, str) or not LOAN_ID_RE.match(holder_id):
        raise ValidationError("holder_id must be a non-empty id string")
    return {
        "policy_type": policy_type,
        "coverage_limit_cents": coverage,
        "deductible_cents": deductible,
        "term_months": term,
        "state": state,
        "holder_id": holder_id,
    }


def compute_premium_cents(cleaned: dict) -> int:
    """Annual-rate premium for the term, in integer cents.

    premium = coverage x rate x state factor x term/12, where rate is the
    base rate less the deductible credit (floored at 1%). All integer math.
    """
    coverage = cleaned["coverage_limit_cents"]
    deductible = cleaned["deductible_cents"]
    deductible_bps = deductible * 10_000 // coverage
    credit_bps = min(deductible_bps, MAX_DEDUCTIBLE_CREDIT_BPS)
    rate_bps = max(BASE_RATE_BPS[cleaned["policy_type"]] - credit_bps, MIN_RATE_BPS)
    factor_pct = STATE_FACTOR_PCT.get(cleaned["state"], DEFAULT_STATE_FACTOR_PCT)
    annual = coverage * rate_bps * factor_pct // (10_000 * 100)
    return annual * cleaned["term_months"] // 12


class QuoteCache:
    """TTL cache for premium quotes (in-memory stand-in for Redis)."""

    def __init__(self, ttl_seconds: int = QUOTE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[int, float]] = {}

    def get(self, key: str) -> int | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._entries[key]
                return None
            return value

    def put(self, key: str, value: int) -> None:
        with self._lock:
            self._entries[key] = (value, time.monotonic() + self._ttl)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class EventPublisher:
    """In-memory event log with Kafka-style topics, keys and offsets.

    A stand-in for a Kafka producer: same ``(topic, key, value)`` records,
    per-topic offsets, no broker. Consumers read with :meth:`events`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._topics: dict[str, list[dict]] = {}

    def publish(self, topic: str, key: str, value: dict) -> dict:
        with self._lock:
            records = self._topics.setdefault(topic, [])
            event = {
                "topic": topic,
                "offset": len(records),
                "key": key,
                "value": value,
            }
            records.append(event)
            return event

    def events(self, topic: str | None = None) -> list[dict]:
        with self._lock:
            if topic is None:
                out: list[dict] = []
                for records in self._topics.values():
                    out.extend(records)
                return out
            return list(self._topics.get(topic, []))

    def count(self, topic: str | None = None) -> int:
        return len(self.events(topic))


@dataclass
class Policy:
    id: str
    holder_id: str
    policy_type: str
    coverage_limit_cents: int
    deductible_cents: int
    term_months: int
    state: str
    premium_cents: int
    status: str = "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "holder_id": self.holder_id,
            "policy_type": self.policy_type,
            "coverage_limit_cents": self.coverage_limit_cents,
            "deductible_cents": self.deductible_cents,
            "term_months": self.term_months,
            "state": self.state,
            "premium_cents": self.premium_cents,
            "status": self.status,
        }


@dataclass
class Claim:
    id: str
    policy_id: str
    amount_cents: int
    description: str
    status: str = "filed"
    payout_cents: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "amount_cents": self.amount_cents,
            "description": self.description,
            "status": self.status,
            "payout_cents": self.payout_cents,
        }


class PolicyStore:
    """Thread-safe in-memory policy and claim store with sequential ids."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._policies: dict[str, Policy] = {}
        self._claims: dict[str, Claim] = {}
        self._policy_counter = 0
        self._claim_counter = 0

    def create_policy(self, cleaned: dict) -> Policy:
        with self._lock:
            self._policy_counter += 1
            policy = Policy(
                id=f"pol_{self._policy_counter:06d}",
                premium_cents=compute_premium_cents(cleaned),
                **cleaned,
            )
            self._policies[policy.id] = policy
            return policy

    def get_policy(self, policy_id: str) -> Policy | None:
        with self._lock:
            return self._policies.get(policy_id)

    def policy_count(self) -> int:
        with self._lock:
            return len(self._policies)

    def file_claim(self, policy: Policy, amount_cents: int, description: str) -> Claim:
        if policy.status != "active":
            raise ValidationError(f"policy {policy.id} is {policy.status}, not active")
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
            raise ValidationError("amount_cents must be an integer number of cents")
        if amount_cents <= 0:
            raise ValidationError("amount_cents must be positive")
        if amount_cents > policy.coverage_limit_cents:
            raise ValidationError(
                "amount_cents exceeds the coverage limit of "
                f"{policy.coverage_limit_cents} cents"
            )
        if not isinstance(description, str) or not description.strip():
            raise ValidationError("description must be a non-empty string")
        with self._lock:
            self._claim_counter += 1
            claim = Claim(
                id=f"clm_{self._claim_counter:06d}",
                policy_id=policy.id,
                amount_cents=amount_cents,
                description=description.strip(),
            )
            self._claims[claim.id] = claim
            return claim

    def get_claim(self, claim_id: str) -> Claim | None:
        with self._lock:
            return self._claims.get(claim_id)

    def claims_for_policy(self, policy_id: str) -> list[Claim]:
        with self._lock:
            return [c for c in self._claims.values() if c.policy_id == policy_id]

    def settle_claim(self, claim: Claim, decision: str) -> Claim:
        if claim.status != "filed":
            raise ValidationError(f"claim {claim.id} is {claim.status}, not filed")
        if decision not in ("approve", "deny"):
            raise ValidationError("decision must be 'approve' or 'deny'")
        with self._lock:
            if decision == "deny":
                claim.status = "denied"
                claim.payout_cents = 0
            else:
                policy = self._policies[claim.policy_id]
                claim.payout_cents = max(
                    claim.amount_cents - policy.deductible_cents, 0
                )
                claim.status = "settled"
            return claim
