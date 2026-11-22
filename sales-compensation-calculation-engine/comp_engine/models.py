"""Data models for the sales compensation calculation engine.

Every record is a plain dataclass so the engine can be tested without a
database. The SQL DDL in SCHEMA_DDL mirrors these models for the warehouse
tables a real deployment would create (Postgres / Snowflake dialect).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Rep:
    rep_id: str
    name: str
    territory: str
    quota: Decimal          # annual quota in dollars
    base_salary: Decimal
    hire_date: date
    active: bool = True


@dataclass(frozen=True)
class Deal:
    deal_id: str
    rep_id: str
    amount: Decimal         # booked ARR / contract value
    close_date: date
    product: str
    territory: str
    status: str = "closed_won"   # closed_won | refunded | churned | pending
    split_with: tuple[str, ...] = ()   # rep_ids sharing credit
    split_pct: Decimal = Decimal("0")  # pct of credit going to split partners


@dataclass(frozen=True)
class Tier:
    """One rung of a tiered rate table: attainment >= threshold pays rate."""
    attainment_threshold: Decimal   # e.g. 0.50 = 50% of quota
    rate: Decimal                   # e.g. 0.08 = 8% commission


@dataclass(frozen=True)
class CompPlan:
    plan_id: str
    name: str
    version: int
    effective_from: date
    effective_to: date | None = None
    tiers: tuple[Tier, ...] = ()
    accelerator_threshold: Decimal = Decimal("1.0")  # attainment above this
    accelerator_multiplier: Decimal = Decimal("1.5")
    cap: Decimal | None = None      # max commission per deal, if any
    clawback_days: int = 90         # churn/refund inside this window claws back


@dataclass(frozen=True)
class Adjustment:
    adjustment_id: str
    deal_id: str
    rep_id: str
    amount: Decimal                 # signed: + bonus, - clawback
    kind: str                       # clawback | manual | spiff
    reason: str
    approved_by: str | None = None
    effective_date: date | None = None


@dataclass
class CommissionResult:
    deal_id: str
    rep_id: str
    plan_id: str
    plan_version: int
    credited_amount: Decimal
    attainment: Decimal
    rate: Decimal
    gross_commission: Decimal
    adjustments: Decimal = Decimal("0")
    net_commission: Decimal = Decimal("0")
    capped: bool = False

    def __post_init__(self) -> None:
        self.net_commission = self.gross_commission + self.adjustments


@dataclass
class Payment:
    payment_id: str
    rep_id: str
    period: str                     # e.g. "2026-11"
    gross_commission: Decimal
    holdback: Decimal
    payable: Decimal
    status: str = "scheduled"      # scheduled | approved | paid | held


SCHEMA_DDL = """
-- Sales compensation warehouse model (Postgres / Snowflake).
CREATE TABLE IF NOT EXISTS comp_reps (
    rep_id      VARCHAR(32) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    territory   VARCHAR(64)  NOT NULL,
    quota       NUMERIC(14,2) NOT NULL,
    base_salary NUMERIC(14,2) NOT NULL,
    hire_date   DATE NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS comp_deals (
    deal_id     VARCHAR(32) PRIMARY KEY,
    rep_id      VARCHAR(32) NOT NULL REFERENCES comp_reps(rep_id),
    amount      NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    close_date  DATE NOT NULL,
    product     VARCHAR(64) NOT NULL,
    territory   VARCHAR(64) NOT NULL,
    status      VARCHAR(16) NOT NULL DEFAULT 'closed_won',
    split_with  VARCHAR(200),
    split_pct   NUMERIC(5,4) NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS comp_plans (
    plan_id     VARCHAR(32) NOT NULL,
    version     INT NOT NULL,
    name        VARCHAR(200) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    PRIMARY KEY (plan_id, version)
);
CREATE TABLE IF NOT EXISTS comp_commissions (
    deal_id     VARCHAR(32) NOT NULL,
    rep_id      VARCHAR(32) NOT NULL,
    plan_id     VARCHAR(32) NOT NULL,
    plan_version INT NOT NULL,
    credited_amount NUMERIC(14,2) NOT NULL,
    attainment  NUMERIC(6,4) NOT NULL,
    rate        NUMERIC(6,4) NOT NULL,
    gross_commission NUMERIC(14,2) NOT NULL,
    net_commission   NUMERIC(14,2) NOT NULL,
    calculated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (deal_id, rep_id)
);
CREATE TABLE IF NOT EXISTS comp_audit_log (
    seq         BIGINT PRIMARY KEY,
    event       VARCHAR(64) NOT NULL,
    entity_id   VARCHAR(64) NOT NULL,
    detail      VARCHAR(1000) NOT NULL,
    prev_hash   CHAR(64) NOT NULL,
    event_hash  CHAR(64) NOT NULL,
    recorded_at TIMESTAMP NOT NULL
);
"""
