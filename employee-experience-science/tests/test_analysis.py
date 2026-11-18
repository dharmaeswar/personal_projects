"""Employee Experience Science — Statistical Analysis of Workplace Experience Data"""

from experience_science.data import generate
from experience_science.defects import find_defects
from experience_science.feedback import benchmark
from experience_science.report import build_report


def test_generate_is_deterministic():
    a = generate()
    b = generate()
    assert a == b
    assert len(a) == 1200


def test_generate_fields_and_ranges():
    rows = generate()
    for r in rows:
        assert 1.0 <= r["experience_score"] <= 5.0
        assert 1.0 <= r["wellbeing_score"] <= 5.0
        assert r["attrition"] in (0, 1)
        assert r["shift"] in ("Day", "Night")
        assert r["feedback_theme"] in (
            "workload", "schedule", "manager", "pay", "growth", "tools")


def test_night_shift_scores_lower():
    rows = generate()
    night = [r["experience_score"] for r in rows if r["shift"] == "Night"]
    day = [r["experience_score"] for r in rows if r["shift"] == "Day"]
    assert sum(night) / len(night) < sum(day) / len(day) - 0.3


def test_overtime_hurts_wellbeing():
    rows = generate()
    hi = [r["wellbeing_score"] for r in rows if r["overtime_hours_week"] > 10]
    lo = [r["wellbeing_score"] for r in rows if r["overtime_hours_week"] <= 10]
    assert sum(hi) / len(hi) < sum(lo) / len(lo)


def test_defects_find_planted_effects():
    rows = generate()
    defects, _ = find_defects(rows)
    by_name = {d["segment"]: d for d in defects}
    night = by_name["Night shift vs Day shift"]
    assert night["confirmed"] is True
    assert night["mean_diff"] < -0.3
    assert night["ci_hi"] < 0  # whole CI below zero
    new_mgr = by_name["New manager (<1y) vs experienced"]
    assert new_mgr["confirmed"] is True
    assert new_mgr["mean_diff"] < -0.2


def test_defects_have_five_segments():
    rows = generate()
    defects, alpha = find_defects(rows)
    assert len(defects) == 5
    assert alpha == 0.05 / 5
    for d in defects:
        assert d["n_in"] > 50 and d["n_out"] > 50
        assert 0.0 <= d["p"] <= 1.0
        assert d["ci_lo"] <= d["mean_diff"] <= d["ci_hi"]


def test_attrition_higher_for_bad_segments():
    rows = generate()
    defects, _ = find_defects(rows)
    by_name = {d["segment"]: d for d in defects}
    night = by_name["Night shift vs Day shift"]
    assert night["attrition_in"] > night["attrition_out"]


def test_feedback_benchmark_beats_baseline():
    rows = generate()
    result = benchmark(rows)
    assert result["accuracy"] > 0.7
    assert result["macro_f1"] > 0.7
    for theme, m in result["per_theme"].items():
        assert m["f1"] > 0.6, theme


def test_report_contains_key_sections():
    rows = generate()
    defects, alpha = find_defects(rows)
    fb = benchmark(rows)
    text = build_report(rows, defects, alpha, fb)
    assert "CONFIRMED EXPERIENCE DEFECTS" in text
    assert "FEEDBACK-THEME BENCHMARK" in text
    assert "WHAT THIS MEANS" in text
    assert "Employees analysed: 1200" in text
