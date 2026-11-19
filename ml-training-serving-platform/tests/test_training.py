import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_platform.data import generate_applications
from ml_platform.training import evaluate, train, train_pipeline


def test_trained_model_beats_chance():
    model, metrics, _ = train_pipeline(n_train=1000, n_test=300, seed=42)
    assert metrics["auc"] > 0.70
    assert metrics["accuracy"] > 0.65


def test_predict_proba_in_unit_range_and_monotone_in_debt_ratio():
    model, _, _ = train_pipeline(n_train=1000, n_test=200, seed=42)
    base = {"income": 80000, "debt_ratio": 0.2, "credit_history_years": 10,
            "delinquencies": 0, "amount": 5000}
    low = model.predict_proba(base)
    high = model.predict_proba({**base, "debt_ratio": 0.8})
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0
    assert high > low  # higher debt ratio -> higher default probability


def test_model_round_trips_through_dict():
    model, _, _ = train_pipeline(n_train=500, n_test=100, seed=42)
    from ml_platform.training import LogisticModel
    restored = LogisticModel.from_dict(model.to_dict())
    features = {"income": 60000, "debt_ratio": 0.4, "credit_history_years": 5,
                "delinquencies": 1, "amount": 8000}
    assert restored.predict_proba(features) == model.predict_proba(features)


def test_evaluate_metrics_are_bounded():
    rows = generate_applications(200, seed=9)
    model = train(rows[:150])
    metrics = evaluate(model, rows[150:])
    for key in ("accuracy", "precision", "recall", "auc"):
        assert 0.0 <= metrics[key] <= 1.0
    assert metrics["n"] == 50
