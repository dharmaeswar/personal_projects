"""Safeguards analytics for a harm-detection model.

Extends the fraud-model validation suite with the analytics a Safeguards
data-science team needs for a harm-detection (content-safety) model:
precision/recall at operating thresholds, false-positive review burden,
score drift monitoring across model versions, and a decision audit trail
that records what the model flagged, what reviewers decided, and what was
overturned.

All data is synthetic and seeded. No real users, content, or harm labels
are used, and nothing here is a claim about any real system.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fraud_validation.monitoring import mean_drift, psi

RNG_SEED = 7
N_EVENTS = 5_000

CATEGORIES = ["violence", "self_harm", "hate", "sexual", "misinformation", "other"]
# Share of truly harmful events per category (synthetic base rates).
CATEGORY_BASE_RATE = {
    "violence": 0.10,
    "self_harm": 0.06,
    "hate": 0.08,
    "sexual": 0.07,
    "misinformation": 0.04,
    "other": 0.02,
}
# Minutes of human review per flagged event, by category (synthetic).
REVIEW_MINUTES = {
    "violence": 6.0,
    "self_harm": 12.0,
    "hate": 5.0,
    "sexual": 8.0,
    "misinformation": 10.0,
    "other": 4.0,
}


def generate_harm_events(n_events: int = N_EVENTS, seed: int = RNG_SEED) -> pd.DataFrame:
    """Generate seeded synthetic harm-detection events with review labels."""
    rng = np.random.default_rng(seed)
    category = rng.choice(CATEGORIES, size=n_events, p=[0.18, 0.10, 0.20, 0.16, 0.20, 0.16])
    base_rate = np.array([CATEGORY_BASE_RATE[c] for c in category])
    # Model score: harmful events score higher on average (real signal).
    is_harmful = rng.binomial(1, base_rate, size=n_events)
    score = np.where(
        is_harmful == 1,
        rng.beta(6.0, 2.0, size=n_events),
        rng.beta(2.0, 6.0, size=n_events),
    )
    week = rng.integers(1, 9, size=n_events)
    return pd.DataFrame(
        {
            "event_id": np.arange(n_events),
            "category": category,
            "week": week,
            "model_score": np.round(score, 4),
            "is_harmful": is_harmful,
        }
    )


def precision_recall_at_thresholds(
    y_true: np.ndarray, y_score: np.ndarray, thresholds=(0.3, 0.5, 0.7, 0.9)
) -> pd.DataFrame:
    """Precision, recall, F1, and flag counts at each operating threshold."""
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    rows = []
    for threshold in thresholds:
        pred = (y_score >= threshold).astype(int)
        tp = int(np.sum((pred == 1) & (y_true == 1)))
        fp = int(np.sum((pred == 1) & (y_true == 0)))
        fn = int(np.sum((pred == 0) & (y_true == 1)))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        rows.append(
            {
                "threshold": float(threshold),
                "flagged": int(np.sum(pred == 1)),
                "true_positives": tp,
                "false_positives": fp,
                "precision": round(float(precision), 4),
                "recall": round(float(recall), 4),
                "f1": round(float(f1), 4),
            }
        )
    return pd.DataFrame(rows)


def false_positive_review(
    events: pd.DataFrame, threshold: float = 0.5
) -> dict:
    """False-positive review burden at the operating threshold.

    Returns the false-positive rate, the share of the review queue that is
    false positives, and the estimated human-review hours the flagged queue
    needs (synthetic per-category review minutes).
    """
    flagged = events[events["model_score"] >= threshold].copy()
    fp = flagged[flagged["is_harmful"] == 0]
    tp = flagged[flagged["is_harmful"] == 1]
    minutes = float(sum(REVIEW_MINUTES[c] for c in flagged["category"])) if len(flagged) else 0.0
    fp_minutes = float(sum(REVIEW_MINUTES[c] for c in fp["category"])) if len(fp) else 0.0
    return {
        "threshold": float(threshold),
        "flagged": int(len(flagged)),
        "false_positives": int(len(fp)),
        "true_positives": int(len(tp)),
        "false_positive_rate": float(len(fp) / len(events)),
        "fp_share_of_queue": float(len(fp) / len(flagged)) if len(flagged) else 0.0,
        "review_hours_total": round(minutes / 60.0, 2),
        "review_hours_wasted_on_fp": round(fp_minutes / 60.0, 2),
    }


def drift_monitor(reference_scores: np.ndarray, current_scores: np.ndarray) -> dict:
    """Score drift between a reference and a current sample (PSI + mean drift)."""
    return {
        "psi": float(psi(reference_scores, current_scores)),
        "mean_drift": float(mean_drift(reference_scores, current_scores)),
        "stable": bool(psi(reference_scores, current_scores) < 0.1),
    }


def build_audit_trail(events: pd.DataFrame, threshold: float = 0.5, seed: int = RNG_SEED) -> pd.DataFrame:
    """Decision audit trail: model decision, reviewer decision, overturn flag.

    Reviewers agree with the model most of the time; a small share of
    model flags are overturned, and a small share of model passes are
    escalated on review. Rates are synthetic and seeded.
    """
    rng = np.random.default_rng(seed + 1)
    flagged = events["model_score"] >= threshold
    # Reviewer agrees with a flag 92% of the time when the event is truly
    # harmful, 70% when it is not (false positives get overturned more).
    agree_prob = np.where(events["is_harmful"] == 1, 0.92, 0.70)
    reviewer_agrees = rng.binomial(1, np.where(flagged, agree_prob, 0.98), size=len(events))
    reviewer_decision = np.where(
        flagged,
        np.where(reviewer_agrees == 1, "uphold", "overturn"),
        np.where(reviewer_agrees == 1, "pass", "escalate"),
    )
    trail = events[["event_id", "category", "week", "model_score", "is_harmful"]].copy()
    trail["threshold"] = float(threshold)
    trail["model_decision"] = np.where(flagged, "flag", "pass")
    trail["reviewer_decision"] = reviewer_decision
    trail["overturned"] = (
        (trail["model_decision"] == "flag") & (trail["reviewer_decision"] == "overturn")
    ) | (
        (trail["model_decision"] == "pass") & (trail["reviewer_decision"] == "escalate")
    )
    return trail


def overturn_rate(audit: pd.DataFrame) -> dict:
    """Overturn rates overall and among flagged events."""
    flagged = audit[audit["model_decision"] == "flag"]
    return {
        "overall_overturn_rate": float(audit["overturned"].mean()),
        "flag_overturn_rate": float(flagged["overturned"].mean()) if len(flagged) else 0.0,
        "n_flagged": int(len(flagged)),
        "n_overturned": int(audit["overturned"].sum()),
    }


def build_safeguards_section(events: pd.DataFrame, threshold: float = 0.5) -> str:
    """Assemble the safeguards analytics report section as plain text."""
    y_true = events["is_harmful"].to_numpy()
    y_score = events["model_score"].to_numpy()
    table = precision_recall_at_thresholds(y_true, y_score)
    review = false_positive_review(events, threshold)
    ref_scores = events[events["week"] <= 4]["model_score"].to_numpy()
    cur_scores = events[events["week"] >= 5]["model_score"].to_numpy()
    drift = drift_monitor(ref_scores, cur_scores)
    audit = build_audit_trail(events, threshold)
    overturn = overturn_rate(audit)

    lines = []
    lines.append("")
    lines.append("7. SAFEGUARDS ANALYTICS (HARM-DETECTION MODEL)")
    lines.append(
        f"   Events: {len(events)} synthetic harm-detection events; "
        f"harmful share: {float(y_true.mean()):.4f}."
    )
    lines.append("   Precision / recall by operating threshold:")
    for _, row in table.iterrows():
        lines.append(
            f"   threshold={row['threshold']:.1f}  flagged={int(row['flagged']):>5d}  "
            f"precision={row['precision']:.3f}  recall={row['recall']:.3f}  f1={row['f1']:.3f}"
        )
    lines.append(
        f"   False-positive review at threshold {threshold}: "
        f"{review['false_positives']} FPs ({review['fp_share_of_queue']:.1%} of the review queue), "
        f"{review['review_hours_total']} review hours, "
        f"{review['review_hours_wasted_on_fp']} hours spent on FPs."
    )
    lines.append(
        f"   Score drift (weeks 1-4 vs 5-8): PSI={drift['psi']:.4f}  "
        f"mean_drift={drift['mean_drift']:+.4f}  "
        f"({'stable' if drift['stable'] else 'shift detected'})."
    )
    lines.append(
        f"   Decision audit trail: {overturn['n_flagged']} flagged, "
        f"{overturn['n_overturned']} overturned overall "
        f"({overturn['overall_overturn_rate']:.1%}); "
        f"flag overturn rate {overturn['flag_overturn_rate']:.1%}."
    )
    return "\n".join(lines)
