"""Sales compensation calculation engine.

End-to-end pipeline: plan versioning -> crediting -> calculation ->
adjustments -> payments, with a hash-chained audit trail and a
three-way reconciliation (CRM vs calculated vs paid).
"""
from .models import (
    Adjustment,
    CommissionResult,
    CompPlan,
    Deal,
    Payment,
    Rep,
    Tier,
)
from .plans import PlanRegistry, PlanError
from .crediting import credit_deal, quota_attainment
from .calculation import calculate, apply_adjustments, rate_for
from .adjustments import AdjustmentError
from .payments import build_payments, approve, mark_paid, release_hold
from .audit import AuditLog
from .reconciliation import reconcile, Finding

__all__ = [
    "Adjustment", "CommissionResult", "CompPlan", "Deal", "Payment", "Rep", "Tier",
    "PlanRegistry", "PlanError", "credit_deal", "quota_attainment",
    "calculate", "apply_adjustments", "rate_for", "AdjustmentError",
    "build_payments", "approve", "mark_paid", "release_hold",
    "AuditLog", "reconcile", "Finding",
]
