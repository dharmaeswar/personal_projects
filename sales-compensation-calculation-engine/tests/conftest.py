"""Shared fixtures: a versioned plan, reps and deals used across tests."""
from datetime import date
from decimal import Decimal

import pytest

from comp_engine import CompPlan, Deal, Rep, Tier, PlanRegistry


@pytest.fixture
def plan_v1():
    return CompPlan(
        plan_id="FY26-AE", name="FY26 Account Executive Plan", version=1,
        effective_from=date(2026, 2, 1), effective_to=date(2026, 10, 31),
        tiers=(Tier(Decimal("0"), Decimal("0.06")),
               Tier(Decimal("0.50"), Decimal("0.08")),
               Tier(Decimal("1.00"), Decimal("0.10"))),
        accelerator_threshold=Decimal("1.0"),
        accelerator_multiplier=Decimal("1.5"),
        cap=Decimal("60000"), clawback_days=90)


@pytest.fixture
def registry(plan_v1):
    reg = PlanRegistry()
    reg.register(plan_v1)
    reg.register(CompPlan(
        plan_id="FY26-AE", name="FY26 Account Executive Plan", version=2,
        effective_from=date(2026, 11, 1),
        tiers=(Tier(Decimal("0"), Decimal("0.06")),
               Tier(Decimal("0.50"), Decimal("0.08")),
               Tier(Decimal("1.00"), Decimal("0.12"))),
        accelerator_threshold=Decimal("1.0"),
        accelerator_multiplier=Decimal("1.5"),
        cap=Decimal("60000"), clawback_days=90))
    return reg


@pytest.fixture
def reps():
    return {
        "R1": Rep("R1", "Ana Ruiz", "West", Decimal("800000"), Decimal("90000"), date(2023, 3, 1)),
        "R2": Rep("R2", "Ben Okafor", "East", Decimal("600000"), Decimal("85000"), date(2024, 1, 15)),
    }


def deal(deal_id="D1", rep_id="R1", amount="100000", close=date(2026, 11, 5), **kw):
    return Deal(deal_id, rep_id, Decimal(amount), close, "Payments", "West", **kw)
