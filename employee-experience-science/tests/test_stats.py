from experience_science.stats import welch_t, chi_square_test, pearson, bootstrap_ci_mean_diff


def test_welch_t_known_difference():
    a = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
    b = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    t, p, d = welch_t(a, b)
    assert t > 5
    assert p < 0.001
    assert d > 2.0


def test_welch_t_identical_samples():
    a = [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    t, p, d = welch_t(a, list(a))
    assert abs(t) < 1e-9
    assert abs(p - 1.0) < 1e-9
    assert abs(d) < 1e-9


def test_chi_square_known_table():
    # Strong association: 40/10 vs 10/40.
    chi2, dof, p = chi_square_test([[40, 10], [10, 40]])
    assert dof == 1
    assert chi2 == 36.0
    assert p < 0.001


def test_chi_square_independent_table():
    chi2, dof, p = chi_square_test([[25, 25], [25, 25]])
    assert chi2 == 0.0
    assert abs(p - 1.0) < 1e-9


def test_pearson_perfect_correlation():
    assert abs(pearson([1, 2, 3, 4], [2, 4, 6, 8]) - 1.0) < 1e-9
    assert abs(pearson([1, 2, 3, 4], [8, 6, 4, 2]) + 1.0) < 1e-9


def test_bootstrap_ci_covers_true_diff():
    a = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    b = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    lo, hi = bootstrap_ci_mean_diff(a, b, n_boot=500, seed=3)
    assert lo > 0  # true difference is +9
    assert lo < 9 < hi
