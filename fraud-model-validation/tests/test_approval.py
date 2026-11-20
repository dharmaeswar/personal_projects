"""Tests for the model approval workflow (fraud_validation/approval.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from fraud_validation.approval import (
    APPROVED,
    APPROVED_WITH_CONDITIONS,
    NOT_APPROVED,
    ApprovalThresholds,
    ModelRecord,
    ValidationEvidence,
    approval_trail_table,
    build_approval_section,
    evaluate_approval,
    evidence_from_results,
    sign_off,
)


def _evidence(**overrides) -> ValidationEvidence:
    base = dict(
        roc_auc=0.90,
        ks=0.60,
        calibration_gap=0.005,
        max_psi=0.02,
        max_flag_rate_gap=0.01,
        n_outcomes=5000,
    )
    base.update(overrides)
    return ValidationEvidence(**base)


def _record() -> ModelRecord:
    return ModelRecord(
        model_id="FRD-001",
        name="Card Fraud Scoring",
        owner="Fraud Analytics",
        model_tier=1,
        purpose="Flag card transactions for review",
    )


def test_clean_evidence_is_approved():
    decision = evaluate_approval(_evidence())
    assert decision.decision == APPROVED
    assert decision.conditions == []
    assert decision.findings == []
    assert all(c["status"] == "PASS" for c in decision.checks)


def test_low_auc_blocks_approval():
    decision = evaluate_approval(_evidence(roc_auc=0.55))
    assert decision.decision == NOT_APPROVED
    assert any("ROC-AUC" in f for f in decision.findings)


def test_low_ks_blocks_approval():
    decision = evaluate_approval(_evidence(ks=0.10))
    assert decision.decision == NOT_APPROVED


def test_small_sample_blocks_approval():
    decision = evaluate_approval(_evidence(n_outcomes=50))
    assert decision.decision == NOT_APPROVED


def test_moderate_psi_gives_conditions_not_rejection():
    decision = evaluate_approval(_evidence(max_psi=0.18))
    assert decision.decision == APPROVED_WITH_CONDITIONS
    assert len(decision.conditions) == 1
    assert decision.findings == []


def test_severe_psi_blocks_approval():
    decision = evaluate_approval(_evidence(max_psi=0.40))
    assert decision.decision == NOT_APPROVED


def test_calibration_bands():
    assert evaluate_approval(_evidence(calibration_gap=0.03)).decision == (
        APPROVED_WITH_CONDITIONS
    )
    assert evaluate_approval(_evidence(calibration_gap=0.09)).decision == NOT_APPROVED


def test_fairness_gap_bands():
    assert evaluate_approval(_evidence(max_flag_rate_gap=0.07)).decision == (
        APPROVED_WITH_CONDITIONS
    )
    assert evaluate_approval(_evidence(max_flag_rate_gap=0.20)).decision == NOT_APPROVED


def test_custom_thresholds_are_respected():
    strict = ApprovalThresholds(min_roc_auc=0.95)
    assert evaluate_approval(_evidence(), strict).decision == NOT_APPROVED
    lax = ApprovalThresholds(psi_fail=0.50)
    assert evaluate_approval(_evidence(max_psi=0.40), lax).decision == (
        APPROVED_WITH_CONDITIONS
    )


def test_evidence_from_results_uses_champion():
    calibration = pd.DataFrame(
        {
            "decile": [1, 2],
            "mean_predicted": [0.10, 0.30],
            "observed_rate": [0.12, 0.28],
            "n": [100, 100],
        }
    )
    results = {"champion": {"roc_auc": 0.88, "ks": 0.55, "calibration": calibration}}
    drift = pd.DataFrame({"column": ["amount"], "mean_drift": [1.0], "psi": [0.03]})
    ev = evidence_from_results(results, drift, max_flag_gap=0.02, n_outcomes=1234)
    assert ev.roc_auc == pytest.approx(0.88)
    assert ev.calibration_gap == pytest.approx(0.02)
    assert ev.max_psi == pytest.approx(0.03)
    assert ev.n_outcomes == 1234


def test_sign_off_and_trail():
    decision = evaluate_approval(_evidence(max_psi=0.18))
    entry = sign_off(_record(), decision, validator="Model Validation", sign_date="2026-11-20")
    assert entry["decision"] == APPROVED_WITH_CONDITIONS
    assert entry["n_conditions"] == 1
    table = approval_trail_table([entry])
    assert list(table["model_id"]) == ["FRD-001"]


def test_approval_section_renders_decision_and_gates():
    decision = evaluate_approval(_evidence())
    entry = sign_off(_record(), decision, validator="Model Validation", sign_date="2026-11-20")
    section = build_approval_section(_record(), decision, entry)
    assert "MODEL APPROVAL WORKFLOW" in section
    assert "Decision: APPROVED" in section
    assert "discrimination_auc" in section
