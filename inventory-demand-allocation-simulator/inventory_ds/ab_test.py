"""A/B test analysis for the two sourcing policies.

Control = nearest-FC sourcing; treatment = cost-optimized (LP) sourcing.
- Fill rate: two-proportion z-test on filled vs unfilled orders.
- Cost per order: Welch's t-test.
Reports effect sizes, 95% confidence intervals, p-values and a go / no-go
recommendation that requires both a significant fill-rate lift and no
significant cost increase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _two_proportion_ci(n1: int, x1: int, n2: int, x2: int) -> tuple[float, float, float]:
    """Difference in proportions (treatment - control) with a 95% Wald CI and z-test p-value."""
    p1, p2 = x1 / n1, x2 / n2
    diff = p2 - p1
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z = diff / se if se > 0 else 0.0
    p_value = float(2 * (1 - stats.norm.cdf(abs(z))))
    return diff, diff - 1.96 * se, diff + 1.96 * se, p_value


def analyse_ab(experiment: pd.DataFrame) -> dict:
    """Analyse the A/B experiment table (columns: group, filled, cost)."""
    control = experiment[experiment["group"] == "control"]
    treat = experiment[experiment["group"] == "treatment"]
    if len(control) == 0 or len(treat) == 0:
        raise ValueError("experiment needs both control and treatment rows")

    n_c, x_c = len(control), int(control["filled"].sum())
    n_t, x_t = len(treat), int(treat["filled"].sum())
    fill_diff, fill_lo, fill_hi, fill_p = _two_proportion_ci(n_c, x_c, n_t, x_t)

    t_res = stats.ttest_ind(treat["cost"], control["cost"], equal_var=False)
    cost_diff = float(treat["cost"].mean() - control["cost"].mean())
    cost_se = float(np.sqrt(treat["cost"].var(ddof=1) / n_t + control["cost"].var(ddof=1) / n_c))
    cost_lo, cost_hi = cost_diff - 1.96 * cost_se, cost_diff + 1.96 * cost_se
    significant_lift = fill_p < 0.05 and fill_lo > 0
    cost_not_worse = cost_hi <= 0.10  # treatment cost may rise at most $0.10/order
    recommendation = (
        "GO — roll out the cost-optimized sourcing policy"
        if significant_lift and cost_not_worse
        else "NO-GO — keep nearest-FC sourcing; rerun with a larger sample or a revised policy"
    )
    return {
        "control_n": n_c, "treatment_n": n_t,
        "control_fill_rate": round(x_c / n_c, 4),
        "treatment_fill_rate": round(x_t / n_t, 4),
        "fill_rate_lift_pp": round(fill_diff * 100, 2),
        "fill_rate_ci_95_pp": (round(float(fill_lo) * 100, 2), round(float(fill_hi) * 100, 2)),
        "fill_rate_p_value": round(fill_p, 6),
        "control_mean_cost": round(float(control["cost"].mean()), 2),
        "treatment_mean_cost": round(float(treat["cost"].mean()), 2),
        "cost_diff_per_order": round(cost_diff, 2),
        "cost_ci_95": (round(float(cost_lo), 2), round(float(cost_hi), 2)),
        "cost_p_value": round(float(t_res.pvalue), 6),
        "recommendation": recommendation,
    }
