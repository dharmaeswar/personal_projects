"""Tests for dataset onboarding: profiling, registry, features, alerts."""

from datetime import date

from investment_data_validation.data import (
    AS_OF,
    build_novel_datasets,
    build_security_master,
    build_trades,
)
from investment_data_validation.dataset_onboarding import (
    build_security_features,
    evaluate_alerts,
    investment_team_summary,
    profile_dataset,
    register_dataset,
    validate_novel_dataset,
)


def _seeded():
    securities = build_security_master()
    trades = build_trades(securities)
    novel = build_novel_datasets(securities)
    return securities, trades, novel


def test_profile_infers_types_and_completeness():
    _, _, novel = _seeded()
    profile = profile_dataset("esg_scores", "Sustainability Data Co.",
                              novel["esg_scores"])
    assert profile.rows == 36
    assert profile.latest_as_of == AS_OF
    by_name = {c.name: c for c in profile.columns}
    assert by_name["esg_score"].inferred_type == "float"
    assert by_name["security_id"].inferred_type == "str"
    assert by_name["as_of_date"].inferred_type == "date"
    # One governance score was planted missing.
    assert by_name["governance"].non_null == 35
    assert by_name["governance"].completeness == 35 / 36


def test_profile_empty_dataset():
    profile = profile_dataset("empty", "No Vendor", [])
    assert profile.rows == 0
    assert profile.columns == []
    assert profile.latest_as_of is None
    assert profile.completeness == 0.0


def test_registry_advances_one_step_only():
    _, _, novel = _seeded()
    registry = {}
    profile = profile_dataset("fx_rates", "FX Rates Ltd.", novel["fx_rates"])
    registered = register_dataset(registry, profile, "Cubist Data Services")
    assert registered.status == "PROFILED"
    assert registered.owner_team == "Cubist Data Services"
    # Skipping straight to LIVE is refused.
    try:
        register_dataset(registry, profile, "Cubist Data Services", "LIVE")
    except ValueError as exc:
        assert "PROFILED to LIVE" in str(exc)
    else:
        raise AssertionError("expected ValueError for a skipped step")
    register_dataset(registry, profile, "Cubist Data Services", "VALIDATED")
    register_dataset(registry, profile, "Cubist Data Services", "LIVE")
    assert registry["fx_rates"].status == "LIVE"


def test_registry_new_dataset_must_start_profiled():
    _, _, novel = _seeded()
    profile = profile_dataset("fx_rates", "FX Rates Ltd.", novel["fx_rates"])
    try:
        register_dataset({}, profile, "Cubist Data Services", "VALIDATED")
    except ValueError as exc:
        assert "must start at PROFILED" in str(exc)
    else:
        raise AssertionError("expected ValueError for a fresh VALIDATED")


def test_features_vwap_and_turnover():
    securities, trades, _ = _seeded()
    features = build_security_features(securities, trades)
    assert len(features) == 40
    by_id = {f.security_id: f for f in features}
    traded = [f for f in features if f.trade_count > 0]
    assert traded, "seeded trades should touch some securities"
    for f in traded:
        assert f.vwap is not None and 85.0 <= f.vwap <= 112.0
        assert f.min_price <= f.vwap <= f.max_price
        assert f.notional is not None and f.notional > 0
        assert f.price_range_pct is not None and f.price_range_pct >= 0
    # Securities with no trades keep null price features, not invented ones.
    untraded = [f for f in features if f.trade_count == 0]
    for f in untraded:
        assert f.vwap is None and f.notional is None


def test_validate_novel_dataset_catches_planted_defects():
    securities, _, novel = _seeded()
    known = {s["security_id"] for s in securities}
    esg = profile_dataset("esg_scores", "Sustainability Data Co.",
                          novel["esg_scores"])
    report = validate_novel_dataset(
        esg, novel["esg_scores"],
        ["security_id", "esg_score", "as_of_date"], as_of=AS_OF)
    assert report.failed == 0  # range problems are warnings, not failures
    assert report.warnings == 2  # missing governance + score above 100

    actions = profile_dataset("corporate_actions", "Actions Wire",
                              novel["corporate_actions"])
    report = validate_novel_dataset(
        actions, novel["corporate_actions"],
        ["action_id", "security_id", "action_type"],
        key_column="action_id", known_ids=known, as_of=AS_OF)
    assert report.failed == 2  # duplicate action_id + orphan security

    fx = profile_dataset("fx_rates", "FX Rates Ltd.", novel["fx_rates"])
    report = validate_novel_dataset(
        fx, novel["fx_rates"], ["pair", "spot_rate", "as_of_date"],
        as_of=AS_OF)
    # One stale row (freshness) + one missing spot rate.
    assert report.warnings == 2


def test_alerts_cover_staleness_completeness_and_drift():
    _, trades, novel = _seeded()
    securities = build_security_master()
    profiles = [
        profile_dataset("esg_scores", "Sustainability Data Co.",
                        novel["esg_scores"]),
        profile_dataset("fx_rates", "FX Rates Ltd.", novel["fx_rates"]),
    ]
    features = build_security_features(securities, trades)
    alerts = evaluate_alerts(profiles, features, {"fx_rates": 6}, AS_OF)
    rules = {(a.rule, a.dataset) for a in alerts}
    assert ("freshness", "fx_rates") in rules  # one stale FX row
    assert ("completeness", "fx_rates") in rules  # missing spot rate (5/6)
    # ESG is 35/36 complete (97.2%): under the 95% default it does not
    # alert, but a stricter 98% bar catches the one missing score.
    assert ("completeness", "esg_scores") not in rules
    strict = evaluate_alerts(profiles, features, {"fx_rates": 6}, AS_OF,
                             min_completeness=0.98)
    assert ("completeness", "esg_scores") in {
        (a.rule, a.dataset) for a in strict
    }
    # The planted bad trade (price -99.5) shows up as a wild price range.
    assert ("feature_range", "security_features") in rules
    assert ("row_count_drift", "fx_rates") not in rules  # 6 rows, no drift
    drifted = evaluate_alerts(profiles, features, {"fx_rates": 4}, AS_OF)
    assert ("row_count_drift", "fx_rates") in {
        (a.rule, a.dataset) for a in drifted
    }


def test_investment_team_summary():
    securities, trades, novel = _seeded()
    profiles = [
        profile_dataset(name, "Vendor", rows)
        for name, rows in novel.items()
    ]
    features = build_security_features(securities, trades)
    alerts = evaluate_alerts(profiles, features, {}, AS_OF)
    summary = investment_team_summary(profiles, features, alerts)
    assert len(summary["datasets"]) == 3
    assert summary["securities_with_trades"] > 0
    assert len(summary["top_by_notional"]) == 3
    assert summary["open_alerts"] == len(alerts)
    top = summary["top_by_notional"][0]
    assert top["notional"] >= summary["top_by_notional"][1]["notional"]
