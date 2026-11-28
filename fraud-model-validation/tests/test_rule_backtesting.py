"""Tests for the card-fraud rule backtesting module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fraud_validation.data import generate_transactions, train_test_split
from fraud_validation.metrics import evaluate_model, tune_threshold
from fraud_validation.models import fit_all, predict_all
from fraud_validation.rule_backtesting import (
    RULES,
    backtest_rules,
    build_rule_backtesting_section,
    combine_flags,
    compute_kris,
    evaluate_rule,
    rule_flags,
    shadow_test,
    staged_rollout,
    tune_score_threshold,
)


@pytest.fixture(scope="module")
def data():
    return generate_transactions()


@pytest.fixture(scope="module")
def test_set(data):
    _, test = train_test_split(data)
    return test


def test_rule_flags_match_manual_definitions(data):
    assert (rule_flags(data, "velocity_1h_burst") == (data["velocity_1h"] >= 5)).all()
    assert (rule_flags(data, "high_amount") == (data["amount"] >= 1000)).all()
    assert (rule_flags(data, "velocity_24h_surge") == (data["velocity_24h"] >= 25)).all()
    night = (data["hour"] < 5) | (data["hour"] >= 23)
    assert (rule_flags(data, "new_device_night") == ((data["device_age_days"] < 30) & night)).all()
    cnp = (data["cross_border"] == 1) & (data["card_present"] == 0) & (data["amount"] >= 200)
    assert (rule_flags(data, "cross_border_cnp_high_amount") == cnp).all()
    with pytest.raises(ValueError):
        rule_flags(data, "not_a_rule")


def test_evaluate_rule_counts_are_consistent(test_set):
    flags = rule_flags(test_set, "velocity_1h_burst")
    result = evaluate_rule(test_set, flags)
    assert result["n_flagged"] == int(flags.sum())
    assert result["fraud_caught"] <= int(test_set["is_fraud"].sum())
    assert result["fraud_caught"] + result["false_positives"] == result["n_flagged"]
    assert 0.0 <= result["precision"] <= 1.0
    assert 0.0 <= result["fraud_capture"] <= 1.0
    assert result["review_cost"] == pytest.approx(result["false_positives"] * 25.0)
    # Fraud loss avoided cannot exceed total fraud loss.
    total_loss = float(test_set.loc[test_set["is_fraud"] == 1, "amount"].sum())
    assert result["fraud_loss_avoided"] <= total_loss
    assert 0.0 <= result["fraud_loss_share"] <= 1.0


def test_backtest_covers_every_rule_plus_combined(test_set):
    table = backtest_rules(test_set)
    assert list(table["rule"]) == RULES + ["ALL_RULES_COMBINED"]
    combined = table.iloc[-1]
    assert combined["n_flagged"] >= table.iloc[:-1]["n_flagged"].max()
    assert combined["fraud_caught"] >= table.iloc[:-1]["fraud_caught"].max()
    # Combined precision is a weighted blend, never above the best single rule
    # once the combined set flags strictly more than any single rule.
    assert combined["precision"] <= table.iloc[:-1]["precision"].max() + 1e-9


def test_combine_flags_is_logical_or(test_set):
    combined = combine_flags(test_set, ["high_amount", "velocity_1h_burst"])
    expected = rule_flags(test_set, "high_amount") | rule_flags(test_set, "velocity_1h_burst")
    assert (combined == expected).all()


def test_shadow_test_deltas_match_sides(test_set):
    champion = ["velocity_1h_burst", "cross_border_cnp_high_amount"]
    challenger = champion + ["new_device_night", "high_amount", "velocity_24h_surge"]
    result = shadow_test(test_set, champion, challenger)
    assert result["deltas"]["fraud_caught"] == (
        result["challenger"]["fraud_caught"] - result["champion"]["fraud_caught"]
    )
    assert result["deltas"]["false_positives"] == (
        result["challenger"]["false_positives"] - result["champion"]["false_positives"]
    )
    # Adding rules can only catch more fraud and flag more false positives.
    assert result["deltas"]["fraud_caught"] >= 0
    assert result["deltas"]["false_positives"] >= 0


def test_staged_rollout_slices_nest_and_grow(test_set):
    flags = combine_flags(test_set, RULES)
    rollout = staged_rollout(test_set, flags)
    assert list(rollout["stage_fraction"]) == [0.10, 0.25, 0.50, 1.00]
    assert rollout["n_transactions"].is_monotonic_increasing
    assert rollout["n_flagged"].is_monotonic_increasing
    assert rollout["fraud_caught"].is_monotonic_increasing
    # Full-exposure stage matches the direct evaluation.
    direct = evaluate_rule(test_set, flags)
    last = rollout.iloc[-1]
    assert int(last["n_flagged"]) == direct["n_flagged"]
    assert int(last["fraud_caught"]) == direct["fraud_caught"]


def test_threshold_tuning_minimises_total_cost(data):
    train, test = train_test_split(data)
    models = fit_all(train)
    scores = predict_all(models, test)
    y_true = test["is_fraud"].to_numpy()
    tuned = tune_score_threshold(y_true, scores["champion"], test["amount"].to_numpy())
    best = tuned["best"]
    table = tuned["table"]
    assert best["total_cost"] == pytest.approx(table["total_cost"].min())
    assert 0.05 <= best["threshold"] <= 0.95
    assert best["total_cost"] <= table.iloc[0]["total_cost"]
    # Every table row's cost is FP x $25 plus missed fraud dollars.
    for _, row in table.iterrows():
        assert row["total_cost"] == pytest.approx(
            row["false_positives"] * 25.0 + row["missed_fraud_loss"]
        )


def test_kris_are_bounded_and_consistent(test_set):
    flags = combine_flags(test_set, RULES)
    kris = compute_kris(test_set, flags)
    assert kris["n_transactions"] == len(test_set)
    assert 0.0 <= kris["flag_rate"] <= 1.0
    assert 0.0 <= kris["approval_rate"] <= 1.0
    assert kris["flag_rate"] + kris["approval_rate"] == pytest.approx(1.0)
    assert kris["alert_volume"] == int(flags.sum())
    assert kris["fraud_loss_per_1000"] > 0
    assert 0.0 <= kris["fraud_capture"] <= 1.0


def test_section_renders_key_numbers(test_set):
    backtest = backtest_rules(test_set)
    shadow = shadow_test(
        test_set,
        ["velocity_1h_burst", "cross_border_cnp_high_amount"],
        RULES,
    )
    rollout = staged_rollout(test_set, combine_flags(test_set, RULES))
    tuned = tune_score_threshold(
        test_set["is_fraud"].to_numpy(),
        np.linspace(0.01, 0.99, len(test_set)),
        test_set["amount"].to_numpy(),
    )
    kris = compute_kris(test_set, combine_flags(test_set, RULES))
    section = build_rule_backtesting_section(backtest, shadow, rollout, tuned, kris)
    assert "Rule Backtesting" in section
    assert "Shadow test" in section
    assert "Staged rollout" in section
    assert "KRIs" in section
    assert "ALL_RULES_COMBINED" in section
