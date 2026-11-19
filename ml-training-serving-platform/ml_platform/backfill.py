"""Offline backfill: re-score historical applications with a model version
and write predictions to CSV, so a new version can be compared against the
old one before promotion.
"""

import csv

from .training import LogisticModel


def backfill(registry, version, rows, out_path):
    """Score rows with the given version; returns (path, n_scored, mean_prob)."""
    entry = registry.get(version)
    if entry is None:
        raise ValueError(f"unknown model version {version}")
    model = LogisticModel.from_dict(entry["model"])
    probs = []
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["application_id", "version", "default_probability", "decision"])
        for i, (features, _label) in enumerate(rows):
            p = model.predict_proba(features)
            probs.append(p)
            writer.writerow([i, version, round(p, 4), "decline" if p >= 0.5 else "approve"])
    mean_prob = sum(probs) / len(probs) if probs else 0.0
    return out_path, len(probs), round(mean_prob, 4)
