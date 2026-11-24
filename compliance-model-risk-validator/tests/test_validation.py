import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import train_test_split

from compliance_model_risk import (
    generate_alert_book,
    generate_monitoring_book,
    train_benchmark,
    train_challenger,
    train_champion,
)
from compliance_model_risk.alert_model import predict_scores
from compliance_model_risk.fairness import (
    disparate_impact_ratio,
    equal_opportunity_gap,
    flag_rates_by_group,
)
from compliance_model_risk.governance import ComplianceModel, ModelInventory
from compliance_model_risk.monitoring import mean_drift_pct, psi
from compliance_model_risk.outcomes import (
    calibration_by_decile,
    decile_capture,
    ks_statistic,
    outcomes_summary,
)
from compliance_model_risk.report import build_report
from compliance_model_risk.threshold import review_burden, threshold_table


@pytest.fixture(scope="module")
def book():
    return generate_alert_book(n=4000, seed=42)


@pytest.fixture(scope="module")
def split(book):
    train, test = train_test_split(
        book, test_size=0.3, random_state=42, stratify=book["sar_worthy"]
    )
    return train, test


@pytest.fixture(scope="module")
def champion(split):
    return train_champion(split[0])


# --- data ---

def test_book_shape_and_label_rate(book):
    assert list(book.columns) == [
        "amount_log",
        "velocity_7d",
        "cross_border",
        "night_flag",
        "new_device",
        "structuring_proximity",
        "sar_worthy",
        "group",
    ]
    assert len(book) == 4000
    assert 0.05 < book["sar_worthy"].mean() < 0.40
    assert set(book["group"].unique()) == {"Group A", "Group B", "Group C"}


def test_book_is_seeded():
    a = generate_alert_book(n=500, seed=1)
    b = generate_alert_book(n=500, seed=1)
    pd.testing.assert_frame_equal(a, b)


def test_monitoring_book_drift_raises_scores():
    base = generate_monitoring_book(n=4000, seed=7, drift=0.0)
    drifted = generate_monitoring_book(n=4000, seed=7, drift=1.0)
    assert drifted["sar_worthy"].mean() > base["sar_worthy"].mean()


# --- models ---

def test_champion_beats_benchmark(split, champion):
    train, test = split
    y = test["sar_worthy"].to_numpy()
    champ = outcomes_summary(y, predict_scores(champion, test))
    bench = outcomes_summary(y, predict_scores(train_benchmark(train), test))
    assert champ["roc_auc"] > 0.70
    assert champ["roc_auc"] > bench["roc_auc"] + 0.10


def test_challenger_trains_and_scores(split):
    train, test = split
    model = train_challenger(train)
    scores = predict_scores(model, test)
    assert len(scores) == len(test)
    assert ((scores >= 0) & (scores <= 1)).all()
    assert outcomes_summary(test["sar_worthy"].to_numpy(), scores)["roc_auc"] > 0.70


def test_benchmark_predicts_base_rate(split):
    train, test = split
    model = train_benchmark(train)
    scores = predict_scores(model, test)
    assert np.allclose(scores, train["sar_worthy"].mean())
    assert outcomes_summary(test["sar_worthy"].to_numpy(), scores)["roc_auc"] == pytest.approx(0.5)


# --- outcomes ---

def test_outcomes_counts_add_up(split, champion):
    _, test = split
    y = test["sar_worthy"].to_numpy()
    o = outcomes_summary(y, predict_scores(champion, test))
    assert o["tp"] + o["fp"] + o["tn"] + o["fn"] == len(test)
    assert o["tp"] + o["fn"] == int(y.sum())
    assert 0.0 <= o["precision"] <= 1.0 and 0.0 <= o["recall"] <= 1.0


def test_ks_known_case():
    y = np.array([0, 0, 0, 1, 1, 1])
    s = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
    assert ks_statistic(y, s) == pytest.approx(1.0)
    assert ks_statistic(y, np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])) == pytest.approx(0.0)


def test_decile_capture_sums_to_100(split, champion):
    _, test = split
    y = test["sar_worthy"].to_numpy()
    deciles = decile_capture(y, predict_scores(champion, test))
    assert len(deciles) == 10
    assert sum(d["capture_pct"] for d in deciles) == pytest.approx(100.0)
    # Top decile must capture more than the bottom decile.
    assert deciles[9]["capture_pct"] > deciles[0]["capture_pct"]


def test_calibration_rows_are_deciles(split, champion):
    _, test = split
    rows = calibration_by_decile(
        test["sar_worthy"].to_numpy(), predict_scores(champion, test)
    )
    assert len(rows) == 10
    assert rows[9]["mean_predicted"] > rows[0]["mean_predicted"]


# --- threshold ---

def test_threshold_table_monotone(split, champion):
    _, test = split
    rows = threshold_table(test["sar_worthy"].to_numpy(), predict_scores(champion, test))
    alerts = [r["alerts"] for r in rows]
    assert alerts == sorted(alerts, reverse=True)
    assert all(r["precision"] >= 0 for r in rows)
    # Higher threshold: fewer alerts, higher precision.
    assert rows[-1]["precision"] >= rows[0]["precision"]


def test_review_burden_arithmetic():
    b = review_burden(300, minutes_per_alert=20.0, investigators=5, hours_per_day=7.5)
    assert b["review_hours"] == pytest.approx(100.0)
    assert b["team_days"] == pytest.approx(100.0 / 37.5, abs=0.01)


# --- monitoring ---

def test_psi_zero_for_identical():
    x = np.random.default_rng(0).normal(0, 1, 2000)
    assert psi(x, x) == pytest.approx(0.0, abs=1e-9)


def test_psi_grows_with_shift():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, 5000)
    shifted = rng.normal(1.5, 1, 5000)
    assert psi(base, shifted) > 0.25


def test_mean_drift_pct():
    assert mean_drift_pct([100.0, 100.0], [110.0, 110.0]) == pytest.approx(10.0)
    assert mean_drift_pct([100.0], [100.0]) == pytest.approx(0.0)


# --- fairness ---

def test_flag_rates_cover_all_groups(split, champion):
    _, test = split
    rates = flag_rates_by_group(test, predict_scores(champion, test))
    assert set(rates) == {"Group A", "Group B", "Group C"}
    for v in rates.values():
        assert 0.0 <= v["flag_rate"] <= 1.0


def test_disparate_impact_ratio_known():
    rates = {"A": {"flag_rate": 0.10}, "B": {"flag_rate": 0.20}}
    assert disparate_impact_ratio(rates) == pytest.approx(0.5)
    assert disparate_impact_ratio({"A": {"flag_rate": 0.1}, "B": {"flag_rate": 0.1}}) == pytest.approx(1.0)


def test_equal_opportunity_gap_known():
    rates = {"A": {"capture_rate": 0.9}, "B": {"capture_rate": 0.7}}
    assert equal_opportunity_gap(rates) == pytest.approx(0.2)


def test_fairness_on_real_scores_is_bounded(split, champion):
    _, test = split
    rates = flag_rates_by_group(test, predict_scores(champion, test))
    assert 0.0 < disparate_impact_ratio(rates) <= 1.0
    assert 0.0 <= equal_opportunity_gap(rates) <= 1.0


# --- governance ---

def test_cadence_by_tier():
    from compliance_model_risk.governance import validation_cadence_days

    assert validation_cadence_days("High") == 365
    assert validation_cadence_days("Medium") == 730
    assert validation_cadence_days("Low") == 1095


def test_overdue_and_gaps():
    m = ComplianceModel("X-1", "Test", "p", "High", owner="", stage="In Use",
                        days_since_validation=400, open_high_findings=2)
    assert m.validation_overdue()
    gaps = m.governance_gaps()
    assert "missing owner" in gaps
    assert "validation overdue" in gaps
    assert any("high finding" in g for g in gaps)

    clean = ComplianceModel("X-2", "Clean", "p", "Low", owner="Team",
                            stage="In Use", days_since_validation=100)
    assert clean.governance_gaps() == []


def test_inventory_gaps_report():
    inv = ModelInventory()
    inv.add(ComplianceModel("X-1", "Late", "p", "High", owner="T", stage="In Use",
                            days_since_validation=500))
    inv.add(ComplianceModel("X-2", "Clean", "p", "Low", owner="T", stage="In Use",
                            days_since_validation=100))
    rows = inv.gaps_report()
    assert rows[0]["gaps"] == ["validation overdue"]
    assert rows[1]["gaps"] == ["clean"]
    assert [m.model_id for m in inv.overdue()] == ["X-1"]


# --- full report ---

def test_build_report_end_to_end(split, champion):
    train, test = split
    later = generate_monitoring_book(n=2000, seed=7, drift=0.15)
    inv = ModelInventory()
    inv.add(ComplianceModel("AML-TM-01", "TM", "p", "High", owner="Ops",
                            stage="In Use", days_since_validation=100))
    report = build_report(
        train, test, later, champion, train_challenger(train),
        train_benchmark(train), inv,
    )
    assert report["verdict"] in ("PASS", "CONDITIONAL")
    assert report["outcomes"]["champion"]["roc_auc"] > 0.70
    assert len(report["decile_capture"]) == 10
    assert len(report["threshold_table"]) == 6
    assert 0.0 <= report["disparate_impact_ratio"] <= 1.0
    assert isinstance(report["findings"], list)
