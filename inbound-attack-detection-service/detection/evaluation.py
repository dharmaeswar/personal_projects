"""Statistical evaluation of the classifier, from scratch.

No scikit-learn: confusion matrix, precision, recall, F1 and ROC-AUC
are computed directly so the numbers in the report are auditable.
"""

from __future__ import annotations


def confusion_matrix(labels: list[int], preds: list[int]) -> dict:
    """Return tp / fp / tn / fn counts for binary 0/1 labels."""
    tp = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 1)
    fp = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 1)
    tn = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 0)
    fn = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 0)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def precision_recall(labels: list[int], preds: list[int]) -> tuple[float, float]:
    """(precision, recall); 0.0 when the denominator is empty."""
    cm = confusion_matrix(labels, preds)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if (cm["tp"] + cm["fp"]) else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if (cm["tp"] + cm["fn"]) else 0.0
    return precision, recall


def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def roc_auc(labels: list[int], scores: list[float]) -> float:
    """ROC-AUC via the Mann-Whitney U statistic (rank based).

    Returns 0.5 when the data has only one class (no discrimination
    is measurable). Ties contribute 0.5.
    """
    positives = [s for y, s in zip(labels, scores) if y == 1]
    negatives = [s for y, s in zip(labels, scores) if y == 0]
    if not positives or not negatives:
        return 0.5
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def evaluate(labels: list[int], scores: list[float], threshold: float) -> dict:
    """Full evaluation at one threshold, plus AUC."""
    preds = [1 if s >= threshold else 0 for s in scores]
    cm = confusion_matrix(labels, preds)
    precision, recall = precision_recall(labels, preds)
    f1 = f1_score(precision, recall)
    return {
        "threshold": threshold,
        "confusion_matrix": cm,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc_auc(labels, scores), 4),
        "accuracy": round(
            (cm["tp"] + cm["tn"]) / max(len(labels), 1), 4
        ),
        "n": len(labels),
        "n_positive": sum(labels),
    }


def evaluate_by_segment(
    labels: list[int],
    scores: list[float],
    segments: list[str],
    threshold: float,
) -> dict[str, dict]:
    """Per-segment precision/recall/F1 (e.g. phishing vs BEC vs bulk)."""
    result: dict[str, dict] = {}
    for segment in sorted(set(segments)):
        idx = [i for i, s in enumerate(segments) if s == segment]
        seg_labels = [labels[i] for i in idx]
        seg_scores = [scores[i] for i in idx]
        result[segment] = evaluate(seg_labels, seg_scores, threshold)
    return result


def threshold_sweep(
    labels: list[int], scores: list[float], thresholds: list[float] | None = None
) -> list[dict]:
    """Precision/recall/F1 at each threshold, for choosing an operating point."""
    if thresholds is None:
        thresholds = [i / 20 for i in range(1, 20)]
    rows = []
    for t in thresholds:
        rows.append(evaluate(labels, scores, t))
    return rows
