"""Tests for the statistics module.

Reference values are textbook critical values, not values copied from the
implementation: t = 2.228 with 10 df is the two-sided 0.05 critical value,
and chi-square = 3.841 with 1 df is the 0.05 critical value.
"""

import math

from agentic_stats import stats


def test_t_cdf_known_values():
    # t = 0 is the median.
    assert stats.t_cdf(0.0, 10) == 0.5
    # Two-sided p for the 0.05 critical value (t = 2.228, df = 10) is 0.05.
    p = 2.0 * (1.0 - stats.t_cdf(2.228, 10))
    assert abs(p - 0.05) < 0.002
    # Large t -> tiny two-sided p.
    p = 2.0 * (1.0 - stats.t_cdf(5.0, 30))
    assert p < 0.0001
    # Symmetry.
    assert abs(stats.t_cdf(-1.5, 8) - (1.0 - stats.t_cdf(1.5, 8))) < 1e-12


def test_welch_t_test_clear_effect():
    a = [10.0, 11.0, 12.0, 11.0, 10.0, 12.0, 11.0, 10.0]
    b = [5.0, 6.0, 5.0, 6.0, 5.0, 6.0, 5.0, 6.0]
    r = stats.welch_t_test(a, b)
    assert r["p"] < 0.0001
    assert abs(r["mean_diff"] - 5.375) < 0.01


def test_welch_t_test_no_effect():
    a = [5.0, 6.0, 7.0, 6.0, 5.0, 7.0]
    b = [6.0, 5.0, 7.0, 5.0, 6.0, 7.0]
    r = stats.welch_t_test(a, b)
    assert r["p"] > 0.5
    assert abs(r["mean_diff"]) < 0.5


def test_chi_square_known_value():
    # chi2 = 3.841, df = 1 is the 0.05 critical value.
    p = 1.0 - stats.gammainc_reg(0.5, 3.841 / 2.0)
    assert abs(p - 0.05) < 0.002


def test_chi_square_test_balanced_table():
    r = stats.chi_square_test([[10, 10], [10, 10]])
    assert abs(r["chi2"]) < 1e-9
    assert abs(r["p"] - 1.0) < 1e-9


def test_chi_square_test_strong_association():
    r = stats.chi_square_test([[40, 10], [10, 40]])
    assert r["p"] < 0.0001
    assert r["df"] == 1


def test_cohens_d():
    d = stats.cohens_d([10.0, 11.0, 12.0], [5.0, 6.0, 7.0])
    assert d > 3.0  # five-point gap, unit-scale spread


def test_bootstrap_ci_covers_true_diff():
    rng_a = [100.0 + i * 0.1 for i in range(60)]
    rng_b = [95.0 + i * 0.1 for i in range(60)]
    lo, hi = stats.bootstrap_ci_mean_diff(rng_a, rng_b, reps=500, seed=1)
    assert lo < 5.0 < hi
    assert lo > 0  # the gap is real


def test_bootstrap_ci_deterministic():
    a = [float(i) for i in range(40)]
    b = [float(i) + 2.0 for i in range(40)]
    first = stats.bootstrap_ci_mean_diff(a, b, seed=3)
    second = stats.bootstrap_ci_mean_diff(a, b, seed=3)
    assert first == second


def test_bonferroni():
    assert stats.bonferroni([0.01, 0.04, 0.20]) == [True, False, False]
    assert stats.bonferroni([0.001, 0.002]) == [True, True]


def test_power_increases_with_effect_and_n():
    assert stats.power_two_sample(0.8, 120) > stats.power_two_sample(0.2, 120)
    assert stats.power_two_sample(0.5, 200) > stats.power_two_sample(0.5, 30)
    assert 0.0 < stats.power_two_sample(0.5, 64) < 1.0


def test_interaction_detects_real_difference():
    # Group A effect is +10, group B effect is 0 -> real interaction.
    a_high = [20.0 + i * 0.2 for i in range(40)]
    b_high = [10.0 + i * 0.2 for i in range(40)]
    a_low = [10.0 + i * 0.2 for i in range(40)]
    b_low = [10.0 + i * 0.2 for i in range(40)]
    r = stats.interaction_t_test(a_high, b_high, a_low, b_low)
    assert r["p"] < 0.0001
    assert abs(r["interaction"] - 10.0) < 0.5


def test_interaction_no_difference():
    a_high = [20.0 + i * 0.2 for i in range(40)]
    b_high = [10.0 + i * 0.2 for i in range(40)]
    a_low = [20.0 + i * 0.2 for i in range(40)]
    b_low = [10.0 + i * 0.2 for i in range(40)]
    r = stats.interaction_t_test(a_high, b_high, a_low, b_low)
    assert r["p"] > 0.5
    assert abs(r["interaction"]) < 0.5
