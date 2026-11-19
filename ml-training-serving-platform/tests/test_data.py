import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_platform.data import FEATURES, generate_applications, to_matrix


def test_generate_returns_requested_rows_with_all_features():
    rows = generate_applications(50, seed=1)
    assert len(rows) == 50
    for features, label in rows:
        assert set(features) == set(FEATURES)
        assert label in (0, 1)


def test_generate_is_reproducible_for_same_seed():
    assert generate_applications(20, seed=3) == generate_applications(20, seed=3)
    assert generate_applications(20, seed=3) != generate_applications(20, seed=4)


def test_labels_have_both_classes():
    rows = generate_applications(500, seed=1)
    labels = {label for _, label in rows}
    assert labels == {0, 1}


def test_to_matrix_shape():
    X, y = to_matrix(generate_applications(10, seed=1))
    assert len(X) == len(y) == 10
    assert all(len(row) == len(FEATURES) for row in X)
