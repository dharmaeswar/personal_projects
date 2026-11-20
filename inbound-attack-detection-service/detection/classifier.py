"""Deterministic, explainable attack-risk scorer.

A weighted linear model over the numeric feature vector, mapped to a
0..1 risk score. This is a rules-plus-weights baseline, not production
detection science: the weights are hand-set priors, and ``train`` only
calibrates the decision threshold (the value that maximises F1 on a
labelled training set). Scores are fully reproducible — same input,
same output — and every prediction lists its top contributing features
so a reviewer can see *why* a message was flagged.
"""

from __future__ import annotations

import math

from .evaluation import f1_score, precision_recall
from .features import extract_features, feature_vector

# Hand-set prior weights. Strong identity/auth signals dominate; weak
# content signals only nudge the score.
DEFAULT_WEIGHTS = {
    "display_name_spoof": 3.0,
    "lookalike_domain": 2.5,
    "dmarc_fail": 0.0,  # folded into auth_failures below
    "auth_failures": 1.2,
    "reply_to_mismatch": 1.5,
    "sender_domain_mismatch": 0.8,
    "free_sender_domain": 0.6,
    "unknown_sender": 0.3,
    "suspicious_tld_count": 1.0,
    "ip_host_url_count": 1.5,
    "url_count": 0.15,
    "risky_attachment_count": 1.2,
    "urgency_keyword_count": 0.4,
    "subject_all_caps": 0.4,
}

DEFAULT_THRESHOLD = 0.5


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class AttackScorer:
    """Weighted-score classifier with a tunable decision threshold."""

    def __init__(self, weights: dict | None = None, threshold: float = DEFAULT_THRESHOLD):
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        self.threshold = threshold

    def score_features(self, features: dict) -> tuple[float, list[tuple[str, float]]]:
        """Return (risk score 0..1, contributions sorted desc by weight)."""
        vector = feature_vector(features)
        raw = 0.0
        contributions: list[tuple[str, float]] = []
        for name, weight in self.weights.items():
            value = vector.get(name, 0.0)
            if name == "dmarc_fail":
                continue
            contrib = weight * value
            raw += contrib
            if contrib:
                contributions.append((name, contrib))
        # Centre the logit so a message with no signals scores near 0.05.
        score = _sigmoid(raw - 2.0)
        contributions.sort(key=lambda item: item[1], reverse=True)
        return score, contributions

    def score_message(self, message: dict, trusted_domain: str = "acmecorp.com") -> dict:
        """Score one message; returns score, label, features, explanation."""
        features = extract_features(message, trusted_domain)
        score, contributions = self.score_features(features)
        return {
            "score": round(score, 4),
            "label": "attack" if score >= self.threshold else "legitimate",
            "features": features,
            "top_signals": [
                {"feature": name, "contribution": round(value, 3)}
                for name, value in contributions[:5]
            ],
        }

    def predict(self, messages: list[dict]) -> list[float]:
        """Risk scores for a list of messages."""
        return [self.score_message(m)["score"] for m in messages]

    def train(self, messages: list[dict], labels: list[int]) -> dict:
        """Calibrate the threshold: pick the value maximising F1.

        Weights are not learned here (too little synthetic data to fit
        them honestly); only the threshold moves. Returns the chosen
        threshold and the F1 achieved at it.
        """
        scores = self.predict(messages)
        best_threshold, best_f1 = self.threshold, -1.0
        for candidate in [i / 100 for i in range(5, 96, 5)]:
            preds = [1 if s >= candidate else 0 for s in scores]
            precision, recall = precision_recall(labels, preds)
            f1 = f1_score(precision, recall)
            if f1 > best_f1:
                best_f1, best_threshold = f1, candidate
        self.threshold = best_threshold
        return {"threshold": best_threshold, "train_f1": round(best_f1, 4)}
