import numpy as np

from dl_credit.metrics import (brier_score, calibration_by_decile,
                               confusion_matrix, decile_capture, gini,
                               ks_statistic, outcomes_summary,
                               precision_recall_f1, psi, roc_auc)


def test_roc_auc_perfect_and_random():
    y = np.array([0, 0, 1, 1])
    assert roc_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert roc_auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    assert roc_auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0


def test_roc_auc_single_class_is_half():
    assert roc_auc(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3])) == 0.5


def test_gini_is_two_auc_minus_one():
    y = np.array([0, 0, 1, 1, 0, 1])
    p = np.array([0.1, 0.4, 0.35, 0.9, 0.2, 0.8])
    assert gini(y, p) == 2 * roc_auc(y, p) - 1


def test_ks_known_value():
    y = np.array([0, 0, 1, 1])
    assert ks_statistic(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert ks_statistic(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.0


def test_confusion_and_prf():
    cm = confusion_matrix([0, 1, 1, 0], [0, 1, 0, 1])
    assert cm == {"tp": 1, "tn": 1, "fp": 1, "fn": 1}
    prf = precision_recall_f1(cm)
    assert prf == {"precision": 0.5, "recall": 0.5, "f1": 0.5}


def test_decile_capture_sums_to_one():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    p = rng.random(500)
    caps = decile_capture(y, p)
    assert len(caps) == 10
    assert abs(sum(caps) - 1.0) < 1e-9


def test_calibration_rows():
    y = np.array([0, 1] * 50)
    p = np.linspace(0.05, 0.95, 100)
    rows = calibration_by_decile(y, p)
    assert len(rows) == 10
    assert rows[0]["n"] == 10
    assert 0 <= rows[-1]["mean_predicted"] <= 1


def test_brier_perfect_is_zero():
    assert brier_score(np.array([0, 1]), np.array([0.0, 1.0])) == 0.0


def test_psi_identical_is_zero():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 1000)
    assert psi(x, x) < 1e-9


def test_psi_shifted_is_large():
    rng = np.random.default_rng(0)
    assert psi(rng.normal(0, 1, 2000), rng.normal(3, 1, 2000)) > 0.25


def test_outcomes_summary_keys():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 200)
    p = rng.random(200)
    s = outcomes_summary(y, p)
    for key in ("roc_auc", "gini", "ks", "brier", "precision", "recall", "f1",
                "top_decile_capture", "max_calibration_gap"):
        assert key in s
    assert 0 <= s["roc_auc"] <= 1
