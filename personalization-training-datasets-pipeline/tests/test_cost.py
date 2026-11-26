import pandas as pd

from personalization_data import cost


def test_advise_balanced_small_frame():
    df = pd.DataFrame({"content_id": ["C1", "C2"] * 50, "v": range(100)})
    out = cost.advise(df)
    assert out["rows"] == 100
    assert out["skew_ratio"] == 1.0
    assert out["estimated_dbu"] == 0.4  # 0.5h x 2 workers x 0.40
    assert "no tuning action needed" in out["advice"][0]


def test_advise_flags_skew():
    df = pd.DataFrame({"content_id": ["C1"] * 90 + ["C2"] * 5 + ["C3"] * 5, "v": range(100)})
    out = cost.advise(df)
    assert out["skew_ratio"] > 3
    assert "skew detected" in out["advice"][0]


def test_advise_empty_frame():
    out = cost.advise(pd.DataFrame())
    assert out["rows"] == 0
    assert out["advice"] == ["empty input: nothing to write"]
