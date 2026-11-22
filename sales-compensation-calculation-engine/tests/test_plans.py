"""Plan versioning: validation, overlap rejection, effective-date lookup."""
from datetime import date
from decimal import Decimal

import pytest

from comp_engine import CompPlan, Tier, PlanRegistry, PlanError


def _plan(version, start, end=None, tiers=None):
    return CompPlan(
        plan_id="P1", name="Plan", version=version,
        effective_from=start, effective_to=end,
        tiers=tiers or (Tier(Decimal("0"), Decimal("0.05")),
                        Tier(Decimal("1.00"), Decimal("0.10"))))


def test_effective_plan_picks_version_by_close_date(registry):
    assert registry.effective_plan("FY26-AE", date(2026, 5, 1)).version == 1
    assert registry.effective_plan("FY26-AE", date(2026, 11, 1)).version == 2


def test_effective_plan_before_any_version_raises(registry):
    with pytest.raises(PlanError):
        registry.effective_plan("FY26-AE", date(2025, 1, 1))


def test_unknown_plan_raises(registry):
    with pytest.raises(PlanError):
        registry.effective_plan("NOPE", date(2026, 5, 1))


def test_overlapping_versions_rejected():
    reg = PlanRegistry()
    reg.register(_plan(1, date(2026, 1, 1), date(2026, 6, 30)))
    with pytest.raises(PlanError):
        reg.register(_plan(2, date(2026, 6, 1)))


def test_duplicate_version_rejected():
    reg = PlanRegistry()
    reg.register(_plan(1, date(2026, 1, 1), date(2026, 6, 30)))
    with pytest.raises(PlanError):
        reg.register(_plan(1, date(2026, 7, 1)))


def test_tiers_must_start_at_zero():
    reg = PlanRegistry()
    bad = _plan(1, date(2026, 1, 1),
                tiers=(Tier(Decimal("0.50"), Decimal("0.08")),))
    with pytest.raises(PlanError):
        reg.register(bad)


def test_tiers_must_be_ordered():
    reg = PlanRegistry()
    bad = _plan(1, date(2026, 1, 1),
                tiers=(Tier(Decimal("1.00"), Decimal("0.10")),
                       Tier(Decimal("0"), Decimal("0.05"))))
    with pytest.raises(PlanError):
        reg.register(bad)


def test_rate_out_of_range_rejected():
    reg = PlanRegistry()
    bad = _plan(1, date(2026, 1, 1),
                tiers=(Tier(Decimal("0"), Decimal("1.50")),))
    with pytest.raises(PlanError):
        reg.register(bad)


def test_accelerator_below_one_rejected():
    reg = PlanRegistry()
    bad = _plan(1, date(2026, 1, 1))
    bad = CompPlan(**{**bad.__dict__, "accelerator_multiplier": Decimal("0.5")})
    with pytest.raises(PlanError):
        reg.register(bad)
