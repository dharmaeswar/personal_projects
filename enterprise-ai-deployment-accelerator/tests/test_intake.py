"""Tests for use-case intake scoring and ranking."""

import pytest

from enterprise_ai_deployment import UseCase, rank_use_cases, score_use_case


def _case(name="Support assistant", value=8, data=9, risk=3):
    return UseCase(name, "IT support", "Answer employee questions.",
                   value=value, data_readiness=data, risk=risk)


def test_score_weights_value_and_data_over_risk():
    result = score_use_case(_case(value=9, data=10, risk=1))
    assert result["score"] == pytest.approx(0.45 * 9 + 0.35 * 10 - 0.20 * 1)
    assert result["tier"] == "scale"


def test_high_risk_case_defers():
    result = score_use_case(_case(value=7, data=4, risk=9))
    assert result["tier"] == "defer"


def test_mid_case_is_pilot():
    result = score_use_case(_case(value=7, data=7, risk=3))
    assert result["score"] == pytest.approx(5.0)
    assert result["tier"] == "pilot"


def test_out_of_range_score_rejected():
    with pytest.raises(ValueError):
        score_use_case(_case(value=11))


def test_ranking_is_best_first():
    ranked = rank_use_cases([
        _case("Low", value=3, data=3, risk=8),
        _case("High", value=9, data=9, risk=2),
    ])
    assert ranked[0]["use_case"].name == "High"
    assert ranked[1]["use_case"].name == "Low"
