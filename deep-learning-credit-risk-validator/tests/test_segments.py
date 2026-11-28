import numpy as np
import pytest

from dl_credit.data import NUMERIC_FEATURES, feature_matrix, generate, standardize, time_split
from dl_credit.segments import kmeans, segment_calibration, segment_summary


def _small_split():
    df = generate(n=800)
    train, val, test = time_split(df)
    Xtr, names = feature_matrix(train)
    Xte, _ = feature_matrix(test)
    Xtr_s, mean, std = standardize(Xtr, Xtr)
    Xte_s = (Xte - mean) / std
    return train, test, Xte_s


def test_kmeans_deterministic_and_covers_all_clusters():
    _, test, Xte_s = _small_split()
    labels1, _, inertia1 = kmeans(Xte_s[:, :len(NUMERIC_FEATURES)], k=4, seed=7)
    labels2, _, inertia2 = kmeans(Xte_s[:, :len(NUMERIC_FEATURES)], k=4, seed=7)
    assert np.array_equal(labels1, labels2)
    assert inertia1 == inertia2
    assert set(labels1.tolist()) == {0, 1, 2, 3}
    assert len(labels1) == len(test)


def test_kmeans_handles_duplicate_points_without_empty_cluster():
    X = np.zeros((20, 3))
    X[:5] = 1.0
    labels, centroids, _ = kmeans(X, k=3, seed=1)
    assert set(labels.tolist()) <= {0, 1, 2}
    assert centroids.shape == (3, 3)
    assert np.isfinite(centroids).all()


def test_kmeans_rejects_empty_input():
    with pytest.raises(ValueError):
        kmeans(np.empty((0, 3)), k=2)


def test_segment_calibration_rows_sum_to_population_and_flag_absurd():
    _, test, Xte_s = _small_split()
    rng = np.random.default_rng(0)
    proba = rng.random(len(test))
    rows, _ = segment_summary(Xte_s[:, :len(NUMERIC_FEATURES)], test, proba)
    assert sum(r["n"] for r in rows) == len(test)
    assert all(0.0 <= r["predicted_rate"] <= 1.0 for r in rows)
    assert all(0.0 <= r["observed_rate"] <= 1.0 for r in rows)
    # Absurd predictions (0.99 everywhere) must flag at least one segment.
    rows_bad = segment_calibration(test, np.full(len(test), 0.99),
                                   np.zeros(len(test), dtype=int))
    assert rows_bad[0]["flagged"] is True
    assert rows_bad[0]["calibration_gap"] > 0.10


def test_segment_calibration_uses_real_outcomes():
    _, test, Xte_s = _small_split()
    # Perfect predictions: predicted == observed per segment, gap ~ 0.
    y = test["defaulted"].to_numpy(dtype=float)
    rows = segment_calibration(test, y, np.zeros(len(test), dtype=int))
    assert rows[0]["calibration_gap"] == pytest.approx(0.0)
    assert rows[0]["observed_rate"] == pytest.approx(float(y.mean()))
