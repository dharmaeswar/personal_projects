"""Production scoring path: model artifact, input checks, batch scoring.

The other modules validate the model; this one is the implementation
phase of the model lifecycle — design, training, evaluation,
validation, then implementation. The trained MLP and its training
standardisation are serialised to a JSON artifact; a fresh scorer
loads the artifact alone (no training code runs) and scores a new
batch of applications the way a production service would. Records
that fail the input schema are rejected with reasons, never silently
scored, and the batch's score-band mix is compared with the reference
book so a shifted applicant mix is visible before the scores are used.
"""
import json

import numpy as np
import pandas as pd

from .data import NUMERIC_FEATURES, feature_matrix
from .mlp import MLPClassifier

ARTIFACT_FORMAT = "dl-credit-mlp/1"

# Plausible input ranges for each numeric application field. A value
# outside these bounds is a data error, not a model input.
FIELD_RANGES = {
    "credit_score": (300.0, 850.0),
    "annual_income": (0.0, 1000000.0),
    "debt_to_income": (0.0, 1.0),
    "revolving_utilization": (0.0, 1.0),
    "history_years": (0.0, 60.0),
    "delinquencies_12m": (0.0, 20.0),
    "inquiries_6m": (0.0, 20.0),
    "open_accounts": (0.0, 50.0),
    "requested_limit": (0.0, 200000.0),
}

SCORE_BANDS = [(0.0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 1.01)]


def export_artifact(model, mean, std, feature_names):
    """Serialise a fitted MLP plus its standardisation to a dict."""
    if model.weights_ is None:
        raise ValueError("model is not fitted")
    return {
        "format": ARTIFACT_FORMAT,
        "hidden": [int(h) for h in model.hidden],
        "feature_names": list(feature_names),
        "mean": [float(v) for v in mean],
        "std": [float(v) for v in std],
        "weights": [[[float(v) for v in row] for row in W]
                    for W in model.weights_],
        "biases": [[float(v) for v in b] for b in model.biases_],
    }


def save_artifact(artifact, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh)


def load_artifact(source):
    """Load an artifact dict (or a path to one); return (model, artifact)."""
    if isinstance(source, (str, bytes)):
        with open(source, encoding="utf-8") as fh:
            artifact = json.load(fh)
    else:
        artifact = source
    if artifact.get("format") != ARTIFACT_FORMAT:
        raise ValueError("unsupported artifact format: %r"
                         % (artifact.get("format"),))
    model = MLPClassifier(hidden=tuple(artifact["hidden"]))
    model.weights_ = [np.array(W, dtype=float) for W in artifact["weights"]]
    model.biases_ = [np.array(b, dtype=float) for b in artifact["biases"]]
    return model, artifact


def check_record(record):
    """Return the list of schema problems for one application record."""
    problems = []
    for field in NUMERIC_FEATURES:
        if field not in record:
            problems.append("missing field: " + field)
            continue
        value = record[field]
        if isinstance(value, bool) or isinstance(value, str):
            problems.append("not a number: " + field)
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            problems.append("not a number: " + field)
            continue
        if not np.isfinite(value):
            problems.append("not finite: " + field)
            continue
        lo, hi = FIELD_RANGES[field]
        if value < lo or value > hi:
            problems.append("out of range [%g, %g]: %s" % (lo, hi, field))
    if "employment_note" not in record:
        problems.append("missing field: employment_note")
    elif not isinstance(record["employment_note"], str):
        problems.append("not text: employment_note")
    return problems


def score_batch(artifact, records):
    """Score a batch of application dicts with the artifact model.

    Returns (scores, rejections): scores is a float array for the
    accepted records, in input order; rejections is a list of
    {"index": i, "problems": [...]} for records that failed the schema.
    """
    model, art = load_artifact(artifact)
    mean = np.array(art["mean"], dtype=float)
    std = np.array(art["std"], dtype=float)
    accepted, rejections = [], []
    for i, record in enumerate(records):
        problems = check_record(record)
        if problems:
            rejections.append({"index": i, "problems": problems})
        else:
            accepted.append(record)
    if not accepted:
        return np.empty(0, dtype=float), rejections
    X, names = feature_matrix(pd.DataFrame(accepted))
    if names != art["feature_names"]:
        raise ValueError("feature order mismatch between artifact and batch")
    return model.predict_proba((X - mean) / std), rejections


def band_distribution(scores, reference_scores):
    """Share of the new batch in each score band vs the reference book."""
    out = []
    for lo, hi in SCORE_BANDS:
        batch_share = (float(np.mean((scores >= lo) & (scores < hi)))
                       if len(scores) else 0.0)
        ref_share = (float(np.mean((reference_scores >= lo)
                                   & (reference_scores < hi)))
                     if len(reference_scores) else 0.0)
        out.append({
            "band": "[%.2f, %.2f)" % (lo, min(hi, 1.0)),
            "batch_share": batch_share,
            "reference_share": ref_share,
            "share_gap": abs(batch_share - ref_share),
        })
    return out
