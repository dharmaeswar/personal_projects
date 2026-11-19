"""Product experimentation: A/B test design, guardrails, sequential monitoring.

Extends the agentic analytics evaluator with the experiment layer a
product data-science team needs: power-based sample-size design, metric
guardrails that stop a harmful rollout, peeking-safe sequential monitoring
(O'Brien-Fleming alpha spending), and a plain-language experiment readout.

Pure standard library, like ``stats.py``. All demo data is synthetic and
seeded; nothing here is a claim about any real product or experiment.
"""

import math

from . import stats

# Acklam's rational approximation coefficients for the inverse normal CDF.
_A = [-3.969683028665376e+01, 2.209460984245205e+02,
      -2.759285984469534e+02, 1.383577518672690e+02,
      -3.066479806614716e+01, 2.506628277459239e+00]
_B = [-5.447609879822406e+01, 1.615858368580409e+02,
      -1.556989798598866e+02, 6.680131188771972e+01,
      -1.328068155288572e+01]
_C = [-7.784894002430293e-03, -3.223964580411365e-01,
      -2.400758277161838e+00, -2.549732539343734e+00,
      4.374664141464968e+00, 2.938163982698783e+00]
_D = [7.784695709041462e-03, 3.224671290700398e-01,
      2.445134137142996e+00, 3.754408661907416e+00]


def norm_ppf(p):
    """Inverse standard-normal CDF (Acklam's approximation, ~1e-9 accuracy)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
            (((( _D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
            (((( _D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / \
        (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)


def required_sample_size(effect_size, alpha=0.05, power=0.80):
    """Users per arm to detect ``effect_size`` (Cohen's d) at given power.

    Normal approximation for a two-sample comparison:
    n = 2 * ((z_{1-a/2} + z_{power}) / d)^2.
    """
    if effect_size <= 0:
        raise ValueError("effect_size must be positive")
    if not 0.0 < alpha < 1.0 or not 0.0 < power < 1.0:
        raise ValueError("alpha and power must be strictly between 0 and 1")
    z_alpha = norm_ppf(1.0 - alpha / 2.0)
    z_beta = norm_ppf(power)
    return int(math.ceil(2.0 * ((z_alpha + z_beta) / effect_size) ** 2))


def design_experiment(baseline_std, mde, daily_users, alpha=0.05, power=0.80):
    """Design an A/B test: sample size per arm and days to run.

    ``mde`` is the minimum detectable effect in outcome units;
    ``baseline_std`` is the outcome's standard deviation.
    """
    if baseline_std <= 0 or mde <= 0 or daily_users <= 0:
        raise ValueError("baseline_std, mde and daily_users must be positive")
    effect_size = mde / baseline_std
    n_per_arm = required_sample_size(effect_size, alpha=alpha, power=power)
    total = 2 * n_per_arm
    days = math.ceil(total / daily_users)
    return {
        "effect_size": round(effect_size, 4),
        "n_per_arm": n_per_arm,
        "total_users": total,
        "days_to_run": days,
        "alpha": alpha,
        "power": power,
    }


def guardrail_check(control, treatment, max_regression, alpha=0.05):
    """Guardrail: fail if the treatment regresses the guardrail metric.

    The guardrail metric must not fall by more than ``max_regression``
    (in outcome units). Fails only when the observed drop exceeds the
    limit *and* the Welch test says the drop is real (p < alpha).
    """
    test = stats.welch_t_test(list(treatment), list(control))
    mean_diff = test["mean_diff"]  # treatment minus control
    breached = mean_diff < -max_regression
    significant = test["p"] < alpha
    return {
        "mean_diff": round(mean_diff, 3),
        "max_regression": max_regression,
        "p": round(test["p"], 4),
        "breached": bool(breached),
        "significant": bool(significant),
        "verdict": "FAIL" if (breached and significant) else "PASS",
    }


def obrien_fleming_boundaries(n_looks, alpha=0.05):
    """O'Brien-Fleming critical z-values for equally spaced interim looks.

    Early looks need overwhelming evidence (high boundary); the final look
    is close to the usual 1.96. This is what makes repeated peeking safe:
    the overall false-positive rate stays at ``alpha``.
    """
    if n_looks < 1:
        raise ValueError("n_looks must be at least 1")
    z_alpha = norm_ppf(1.0 - alpha / 2.0)
    return [round(z_alpha / math.sqrt(k / n_looks), 3) for k in range(1, n_looks + 1)]


def sequential_decision(z_values, boundaries):
    """First look at which |z| crosses its O'Brien-Fleming boundary, or None."""
    if len(z_values) != len(boundaries):
        raise ValueError("z_values and boundaries must have the same length")
    for i, (z, boundary) in enumerate(zip(z_values, boundaries), start=1):
        if abs(z) >= boundary:
            return {"stop_at_look": i, "z": round(z, 3), "boundary": boundary}
    return {"stop_at_look": None, "z": None, "boundary": None}


def experiment_readout(rows, primary="primary", guardrail="secondary", mde=5.0, daily_users=1000):
    """Full experiment readout for a two-arm dataset (list of row dicts)."""
    from .data import split_arms

    control, treatment = split_arms(rows)
    a = [r[primary] for r in treatment]
    b = [r[primary] for r in control]
    test = stats.welch_t_test(a, b)
    lo, hi = stats.bootstrap_ci_mean_diff(a, b)
    d = stats.cohens_d(a, b)
    power = stats.power_two_sample(abs(d), len(a))
    pooled_std = stats.std(a + b, ddof=1)
    design = design_experiment(pooled_std, mde, daily_users)
    guard = guardrail_check(
        [r[guardrail] for r in control],
        [r[guardrail] for r in treatment],
        max_regression=5.0,
    )
    return {
        "n_per_arm": len(a),
        "mean_diff": round(test["mean_diff"], 2),
        "p": round(test["p"], 6),
        "ci_95": (round(lo, 2), round(hi, 2)),
        "cohens_d": round(d, 3),
        "power": round(power, 3),
        "significant": bool(test["p"] < 0.05 and lo > 0),
        "required_n_per_arm": design["n_per_arm"],
        "adequately_powered": bool(len(a) >= design["n_per_arm"]),
        "days_to_run": design["days_to_run"],
        "guardrail": guard,
    }


def build_experiment_section(rows, mde=5.0):
    """Assemble the product-experimentation report section as plain text."""
    readout = experiment_readout(rows, mde=mde)
    boundaries = obrien_fleming_boundaries(4)
    lines = []
    lines.append("")
    lines.append("PRODUCT EXPERIMENTATION (A/B TEST READOUT)")
    lines.append(
        f"   Primary outcome: mean difference {readout['mean_diff']:+.2f}, "
        f"p = {readout['p']:.4g}, 95% CI {readout['ci_95']}, "
        f"Cohen's d = {readout['cohens_d']}."
    )
    lines.append(
        f"   Power: {readout['power']} at n = {readout['n_per_arm']} per arm; "
        f"design needs {readout['required_n_per_arm']} per arm for MDE {mde} "
        f"({'adequately powered' if readout['adequately_powered'] else 'UNDER-POWERED for this MDE'})."
    )
    lines.append(
        f"   Verdict: {'SHIP' if readout['significant'] and readout['guardrail']['verdict'] == 'PASS' else 'DO NOT SHIP'} "
        f"({'significant' if readout['significant'] else 'not significant'}; "
        f"guardrail {readout['guardrail']['verdict']}, "
        f"mean diff {readout['guardrail']['mean_diff']:+.2f})."
    )
    lines.append(
        "   O'Brien-Fleming boundaries for 4 equally spaced looks: "
        + ", ".join(f"{b:.2f}" for b in boundaries)
        + " (early looks need stronger evidence, so peeking stays safe)."
    )
    return "\n".join(lines)
