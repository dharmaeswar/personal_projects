"""Load-sheet reporting: text and JSON views of a finalized load plan."""

from __future__ import annotations

import json

from .load_plan import LoadPlan


def text_load_sheet(plan: LoadPlan) -> str:
    if plan.result is None:
        raise ValueError("finalize() must run before reporting")
    r = plan.result
    lines = [
        f"LOAD SHEET — flight {plan.flight}",
        f"Total weight: {r.total_weight_lb:,.0f} lb",
        f"CG: {r.cg_arm_in:.1f} in ({r.cg_percent_mac:.2f}% MAC), "
        f"limits {r.fwd_limit:.1f}–{r.aft_limit:.1f}% MAC",
        f"Envelope: {'WITHIN' if r.within_envelope else 'OUT OF'} limits",
    ]
    for comp, total in sorted(plan.compartment_totals().items()):
        lines.append(f"  {comp} hold: {total:,.0f} lb")
    for item in plan.items:
        lines.append(f"  {item.name}: {item.weight_lb:,.0f} lb @ {item.arm_in:.0f} in")
    for v in r.violations:
        lines.append(f"  VIOLATION: {v}")
    return "\n".join(lines)


def json_load_sheet(plan: LoadPlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True)
