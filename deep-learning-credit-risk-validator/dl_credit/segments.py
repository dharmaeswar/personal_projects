"""Applicant segmentation for the deep-learning credit-risk validator.

K-means clustering (from scratch in NumPy) groups the scored population
into risk segments, and each segment is then backtested on its own:
predicted vs realised default rate, with a flag when the calibration
gap is wider than 0.10. A model can look calibrated overall while
mispricing one segment — for example thin-file applicants — so the
segment table is part of the validation report.

The JD for this role lists clustering alongside classification, time
series and deep learning; the rest of the validator already covers the
other three, so this module closes that gap.
"""
import numpy as np


def kmeans(X, k=4, seed=7, max_iter=100, tol=1e-4):
    """Lloyd's algorithm with k-means++ style seeding.

    Returns (labels, centroids, inertia). Empty clusters are re-seeded
    to the point farthest from its assigned centroid, so every cluster
    keeps at least one member.
    """
    X = np.asarray(X, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(X)
    if n == 0:
        raise ValueError("kmeans needs at least one row")
    if k < 1:
        raise ValueError("k must be at least 1")
    k = min(k, n)

    # k-means++ seeding: first centre uniform, then weighted by distance.
    centres = [X[rng.integers(n)]]
    closest_sq = np.sum((X - centres[0]) ** 2, axis=1)
    for _ in range(1, k):
        total = float(closest_sq.sum())
        if total <= 0:
            centres.append(X[rng.integers(n)])
        else:
            probs = closest_sq / total
            centres.append(X[rng.choice(n, p=probs)])
        closest_sq = np.minimum(
            closest_sq, np.sum((X - centres[-1]) ** 2, axis=1))
    centroids = np.array(centres, dtype=float)

    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        dists = np.sum((X[:, None, :] - centroids[None, :, :]) ** 2, axis=2)
        new_labels = np.argmin(dists, axis=1)
        new_centroids = centroids.copy()
        for j in range(k):
            members = X[new_labels == j]
            if len(members):
                new_centroids[j] = members.mean(axis=0)
            else:
                # Re-seed an empty cluster on the worst-fit point.
                worst = int(np.argmax(np.min(dists, axis=1)))
                new_centroids[j] = X[worst]
        shift = float(np.max(np.abs(new_centroids - centroids)))
        labels, centroids = new_labels, new_centroids
        if shift < tol:
            break
    inertia = float(np.sum((X - centroids[labels]) ** 2))
    return labels, centroids, inertia


def segment_calibration(df, proba, labels):
    """Per-segment predicted vs observed default rate with a gap flag."""
    proba = np.asarray(proba, dtype=float)
    labels = np.asarray(labels)
    rows = []
    for seg in sorted(set(int(l) for l in labels)):
        mask = labels == seg
        group = df[mask]
        pred = float(proba[mask].mean())
        obs = float(group["defaulted"].mean())
        rows.append({
            "segment": int(seg),
            "n": int(mask.sum()),
            "mean_credit_score": float(group["credit_score"].mean()),
            "predicted_rate": pred,
            "observed_rate": obs,
            "calibration_gap": float(abs(pred - obs)),
            "flagged": bool(abs(pred - obs) > 0.10),
        })
    return rows


def segment_summary(X_numeric, df, proba, k=4, seed=7):
    """Cluster the population and backtest each segment.

    X_numeric must be the standardised numeric features (same rows as
    df, same order as proba). Returns (rows, inertia).
    """
    labels, _, inertia = kmeans(X_numeric, k=k, seed=seed)
    return segment_calibration(df, proba, labels), float(inertia)
