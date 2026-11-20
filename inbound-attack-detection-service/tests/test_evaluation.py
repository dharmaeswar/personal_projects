"""Tests for evaluation math, using hand-built cases with known answers."""

from detection.evaluation import (
    confusion_matrix,
    evaluate,
    evaluate_by_segment,
    f1_score,
    precision_recall,
    roc_auc,
    threshold_sweep,
)


def test_confusion_matrix_counts():
    cm = confusion_matrix([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert cm == {"tp": 2, "fp": 1, "tn": 1, "fn": 1}


def test_precision_recall_known_values():
    # 2 TP, 1 FP, 1 FN -> precision 2/3, recall 2/3
    precision, recall = precision_recall([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert precision == 2 / 3
    assert recall == 2 / 3


def test_precision_recall_empty_denominator_is_zero():
    precision, recall = precision_recall([0, 0], [0, 0])
    assert precision == 0.0 and recall == 0.0


def test_f1_known_value():
    assert f1_score(0.5, 1.0) == 2 * 0.5 * 1.0 / 1.5
    assert f1_score(0.0, 0.0) == 0.0


def test_roc_auc_perfect_separation():
    assert roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0


def test_roc_auc_worst_separation():
    assert roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0


def test_roc_auc_ties_count_half():
    # positives 0.5, 0.5 vs negatives 0.5, 0.1 -> wins: 0.5+0.5+1+1 = 3 / 4
    assert roc_auc([1, 1, 0, 0], [0.5, 0.5, 0.5, 0.1]) == 0.75


def test_roc_auc_single_class_is_half():
    assert roc_auc([1, 1, 1], [0.2, 0.5, 0.9]) == 0.5


def test_evaluate_known_case():
    result = evaluate([1, 1, 0, 0], [0.9, 0.4, 0.8, 0.1], threshold=0.5)
    assert result["confusion_matrix"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["roc_auc"] == 0.75


def test_evaluate_by_segment_slices():
    labels = [1, 1, 0, 0]
    scores = [0.9, 0.9, 0.1, 0.1]
    segments = ["phishing", "bec", "legitimate", "bulk"]
    out = evaluate_by_segment(labels, scores, segments, 0.5)
    assert set(out) == {"phishing", "bec", "legitimate", "bulk"}
    assert out["phishing"]["precision"] == 1.0
    assert out["bulk"]["precision"] == 0.0  # no positives predicted in bulk


def test_threshold_sweep_monotonic_recall():
    labels = [1, 1, 0, 0]
    scores = [0.9, 0.6, 0.4, 0.1]
    rows = threshold_sweep(labels, scores, thresholds=[0.9, 0.5, 0.2])
    assert len(rows) == 3
    assert rows[0]["recall"] <= rows[1]["recall"] <= rows[2]["recall"]
    assert rows[0]["precision"] >= rows[2]["precision"]
