"""Comp plan versioning: register plan versions and resolve the version
in force on a given date. Plan changes never rewrite history — a deal is
always calculated under the version effective on its close date.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import CompPlan


class PlanError(ValueError):
    pass


def validate_plan(plan: CompPlan) -> None:
    """A plan is valid only if its tiers are ordered, rates are sane and
    the accelerator is a real multiplier."""
    if not plan.tiers:
        raise PlanError(f"plan {plan.plan_id} v{plan.version}: no tiers")
    thresholds = [t.attainment_threshold for t in plan.tiers]
    if thresholds != sorted(thresholds):
        raise PlanError(f"plan {plan.plan_id} v{plan.version}: tiers out of order")
    if thresholds[0] != Decimal("0"):
        raise PlanError(f"plan {plan.plan_id} v{plan.version}: first tier must start at 0")
    for tier in plan.tiers:
        if not (Decimal("0") < tier.rate <= Decimal("1")):
            raise PlanError(f"plan {plan.plan_id} v{plan.version}: rate {tier.rate} out of range")
    if plan.accelerator_multiplier < Decimal("1"):
        raise PlanError("accelerator multiplier must be >= 1")
    if plan.cap is not None and plan.cap < 0:
        raise PlanError("cap must be >= 0")
    if plan.effective_to is not None and plan.effective_to < plan.effective_from:
        raise PlanError("effective_to before effective_from")


class PlanRegistry:
    """All versions of all plans, keyed by plan_id."""

    def __init__(self) -> None:
        self._plans: dict[str, list[CompPlan]] = {}

    def register(self, plan: CompPlan) -> None:
        validate_plan(plan)
        versions = self._plans.setdefault(plan.plan_id, [])
        if any(p.version == plan.version for p in versions):
            raise PlanError(f"plan {plan.plan_id} v{plan.version} already registered")
        for existing in versions:
            if _overlaps(existing, plan):
                raise PlanError(
                    f"plan {plan.plan_id} v{plan.version} overlaps v{existing.version} "
                    f"({existing.effective_from}..{existing.effective_to})"
                )
        versions.append(plan)
        versions.sort(key=lambda p: p.effective_from)

    def effective_plan(self, plan_id: str, on: date) -> CompPlan:
        """The version in force on `on`; raises if none covers that date."""
        for plan in self._plans.get(plan_id, []):
            if plan.effective_from <= on and (plan.effective_to is None or on <= plan.effective_to):
                return plan
        raise PlanError(f"no version of plan {plan_id} effective on {on}")

    def versions(self, plan_id: str) -> list[CompPlan]:
        return list(self._plans.get(plan_id, []))


def _overlaps(a: CompPlan, b: CompPlan) -> bool:
    a_end = a.effective_to or date.max
    b_end = b.effective_to or date.max
    return a.effective_from <= b_end and b.effective_from <= a_end
