"""Tests for the weighted-score classifier."""

from detection.classifier import AttackScorer
from detection.features import extract_features
from tests.test_features import LEGIT, PHISH


def test_legit_scores_low_and_phish_scores_high():
    scorer = AttackScorer()
    legit = scorer.score_message(LEGIT)
    phish = scorer.score_message(PHISH)
    assert legit["score"] < 0.5
    assert legit["label"] == "legitimate"
    assert phish["score"] >= 0.5
    assert phish["label"] == "attack"


def test_scoring_is_deterministic():
    scorer = AttackScorer()
    assert scorer.score_message(PHISH) == scorer.score_message(PHISH)


def test_top_signals_explain_the_flag():
    scorer = AttackScorer()
    result = scorer.score_message(PHISH)
    names = [s["feature"] for s in result["top_signals"]]
    assert "display_name_spoof" in names
    assert all(s["contribution"] > 0 for s in result["top_signals"])


def test_empty_message_scores_near_zero():
    scorer = AttackScorer()
    result = scorer.score_message({"sender": "a@acmecorp.com"})
    assert result["score"] < 0.2


def test_threshold_moves_the_label():
    scorer = AttackScorer(threshold=1.0)  # no score can reach 1.0
    assert scorer.score_message(PHISH)["label"] == "legitimate"
    scorer.threshold = 0.01
    assert scorer.score_message(LEGIT)["label"] == "attack"


def test_train_calibrates_threshold_on_synthetic_data():
    from detection.pipeline import generate_dataset

    messages = generate_dataset(seed=7)
    labels = [m["label"] for m in messages]
    scorer = AttackScorer()
    info = scorer.train(messages, labels)
    assert 0.05 <= info["threshold"] <= 0.95
    assert info["train_f1"] > 0.8  # synthetic data is strongly separable


def test_predict_returns_one_score_per_message():
    scorer = AttackScorer()
    scores = scorer.predict([LEGIT, PHISH, LEGIT])
    assert len(scores) == 3
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_score_features_returns_contributions():
    scorer = AttackScorer()
    score, contribs = scorer.score_features(extract_features(PHISH))
    assert 0.0 <= score <= 1.0
    assert contribs[0][1] >= contribs[-1][1]  # sorted descending
