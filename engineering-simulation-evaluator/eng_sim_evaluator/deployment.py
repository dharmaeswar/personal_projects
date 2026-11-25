"""Model deployment: turn a validated model into a software-ready artifact.

The Landmark workflow ends by helping software engineers integrate a tested
model into software, cloud, or operational environments. This module does
the handoff properly: a JSON artifact a service can load without the
training code, a pure-NumPy predict function with the same maths, and a
deployment checklist naming each step and its gate.
"""

from __future__ import annotations

import json

import numpy as np

from .energy_model import FEATURES, OlsModel, Standardiser

ARTIFACT_VERSION = "energy-rop-v1"


def export_model_artifact(ols: OlsModel, validation: dict,
                          dictionary_version: str) -> dict:
    """Serialise the fitted OLS model as a deployable JSON artifact."""
    assert ols.coef_ is not None and ols.intercept_ is not None
    std = ols.standardiser
    assert std.mean_ is not None and std.scale_ is not None
    return {
        "artifact_version": ARTIFACT_VERSION,
        "model_type": "ols_standardised_features",
        "target": "rop_ft_hr",
        "data_dictionary_version": dictionary_version,
        "features": FEATURES,
        "feature_mean": [float(v) for v in std.mean_],
        "feature_scale": [float(v) for v in std.scale_],
        "coefficients": [float(v) for v in ols.coef_],
        "intercept": float(ols.intercept_),
        "holdout_metrics": validation["ols"],
        "prediction_clip_ft_hr": [0.5, 120.0],
    }


def save_artifact(artifact: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2)


def load_artifact(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def predict_from_artifact(artifact: dict, row: dict) -> float:
    """Predict ROP from a plain dict of raw feature values, using only the
    artifact — no training code, no fitted objects. This is the function a
    software engineer embeds in the energy software."""
    features = artifact["features"]
    mean = np.array(artifact["feature_mean"], dtype=float)
    scale = np.array(artifact["feature_scale"], dtype=float)
    coef = np.array(artifact["coefficients"], dtype=float)
    x = np.array([float(row[name]) for name in features], dtype=float)
    standardised = (x - mean) / scale
    prediction = float(artifact["intercept"] + standardised @ coef)
    lo, hi = artifact["prediction_clip_ft_hr"]
    return min(max(prediction, lo), hi)


def rebuild_ols_from_artifact(artifact: dict) -> OlsModel:
    """Rebuild an OlsModel from an artifact, for parity checks."""
    model = OlsModel()
    std = Standardiser()
    std.mean_ = np.array(artifact["feature_mean"], dtype=float)
    std.scale_ = np.array(artifact["feature_scale"], dtype=float)
    model.standardiser = std
    model.coef_ = np.array(artifact["coefficients"], dtype=float)
    model.intercept_ = float(artifact["intercept"])
    return model


def deployment_checklist() -> list[dict]:
    """Ordered deployment steps, each with its gate. A step is done only
    when its gate passes — the same discipline as the CI guardrails."""
    return [
        {
            "step": 1,
            "action": "Schema check: incoming telemetry must match the data "
                      "dictionary (field names, units, valid ranges).",
            "gate": "No field outside its valid range reaches the model.",
        },
        {
            "step": 2,
            "action": "Load the model artifact and run the parity check: "
                      "predict_from_artifact must match the training-time "
                      "model on a frozen test set.",
            "gate": "Max absolute difference below 1e-6 ft/hr.",
        },
        {
            "step": 3,
            "action": "Shadow run: run the model alongside the current "
                      "method for one drilling campaign and compare ROP "
                      "predictions with the analytic ground truth.",
            "gate": "Shadow MAE within 10% of the validated holdout MAE.",
        },
        {
            "step": 4,
            "action": "Wire monitoring: track input ranges, missing-value "
                      "rate and prediction drift against the holdout "
                      "baseline; alert on 3-sigma ROP residuals.",
            "gate": "Alerts fire in a dry run before go-live.",
        },
        {
            "step": 5,
            "action": "Document the model card (methods, assumptions, "
                      "limitations) next to the artifact and version both "
                      "together.",
            "gate": "Model card and artifact share the same version string.",
        },
        {
            "step": 6,
            "action": "Plan rollback: keep the previous model version live "
                      "until the new one passes its first monitored week.",
            "gate": "Rollback rehearsed and timed.",
        },
    ]
