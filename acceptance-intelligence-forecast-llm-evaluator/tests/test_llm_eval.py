import pytest

from acceptance_eval import (
    score_grounding, score_completeness, paired_comparison, bonferroni,
)


def test_grounding_fully_grounded_note():
    computed = {"mae": 0.0123, "rmse": 0.0156}
    res = score_grounding("MAE 0.0123 and RMSE 0.0156 look good.", computed)
    assert res["grounding_rate"] == 1.0
    assert res["unsupported"] == []


def test_grounding_flags_invented_number():
    computed = {"mae": 0.0123}
    res = score_grounding("MAE 0.001 and accuracy 99.9 are excellent.", computed)
    assert res["grounding_rate"] < 1.0
    assert 0.001 in res["unsupported"]
    assert 99.9 in res["unsupported"]


def test_grounding_matches_percent_scale():
    computed = {"rate": 0.865}
    res = score_grounding("Acceptance is 86.5 percent.", computed)
    assert res["grounding_rate"] == 1.0


def test_grounding_empty_text_is_vacuous():
    res = score_grounding("No numbers here.", {"mae": 0.01})
    assert res["cited"] == 0
    assert res["grounding_rate"] == 1.0


def test_completeness_partial():
    res = score_completeness("The forecast shows drift.",
                             ["forecast", "mae", "drift"])
    assert res["completeness"] == pytest.approx(2 / 3)
    assert res["missing"] == ["mae"]


def test_paired_comparison_clear_win():
    base = [0.72, 0.68, 0.75, 0.70, 0.74, 0.69, 0.73, 0.71, 0.76, 0.70]
    tuned = [0.81, 0.79, 0.83, 0.80, 0.82, 0.78, 0.84, 0.80, 0.85, 0.79]
    res = paired_comparison(base, tuned)
    assert res["win_rate"] == 1.0
    assert res["mean_diff"] == pytest.approx(0.093, abs=1e-9)
    assert res["ci_95"][0] > 0  # whole CI above zero: real improvement
    assert 0 <= res["p_value"] <= 0.01


def test_paired_comparison_deterministic():
    base = [0.5, 0.6, 0.7]
    tuned = [0.6, 0.6, 0.8]
    assert paired_comparison(base, tuned) == paired_comparison(base, tuned)


def test_paired_comparison_rejects_mismatched():
    with pytest.raises(ValueError):
        paired_comparison([0.5], [0.5, 0.6])


def test_bonferroni_caps_at_one():
    assert bonferroni([0.01, 0.04, 0.30]) == pytest.approx([0.03, 0.12, 0.90])
    assert bonferroni([0.6, 0.7]) == [1.0, 1.0]
