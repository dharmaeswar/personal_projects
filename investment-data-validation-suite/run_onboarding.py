"""End-to-end demo: onboard three novel vendor datasets for a systematic
data-services team — profile, validate, build features, raise alerts, and
summarise preliminary analysis for investment teams."""

import json

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

VENDORS = {
    "esg_scores": "Sustainability Data Co.",
    "corporate_actions": "Actions Wire",
    "fx_rates": "FX Rates Ltd.",
}
REQUIRED = {
    "esg_scores": ["security_id", "esg_score", "as_of_date"],
    "corporate_actions": ["action_id", "security_id", "action_type"],
    "fx_rates": ["pair", "spot_rate", "as_of_date"],
}


def main() -> None:
    securities = build_security_master()
    trades = build_trades(securities)
    novel = build_novel_datasets(securities)
    known_ids = {s["security_id"] for s in securities}
    registry = {}
    profiles = []
    for name, rows in novel.items():
        profile = profile_dataset(name, VENDORS[name], rows)
        register_dataset(registry, profile, "Cubist Data Services")
        register_dataset(registry, profile, "Cubist Data Services",
                         "VALIDATED")
        profiles.append(profile)
        report = validate_novel_dataset(
            profile, rows, REQUIRED[name],
            key_column="action_id" if name == "corporate_actions" else None,
            known_ids=known_ids if name != "fx_rates" else None,
            as_of=AS_OF,
        )
        print(f"{name}: {report.records_checked} rows, "
              f"{report.checks_run} checks, {report.passed} passed, "
              f"{report.failed} failed, {report.warnings} warnings")
        for f in report.findings:
            print(f"  [{f.severity}] {f.check} {f.record_id}: {f.message}")
    features = build_security_features(securities, trades)
    alerts = evaluate_alerts(profiles, features, {}, AS_OF)
    print(f"FEATURES: {len(features)} securities, "
          f"{sum(1 for f in features if f.trade_count > 0)} with trades")
    print(f"ALERTS: {len(alerts)} open")
    for a in alerts:
        print(f"  [{a.severity}] {a.rule} {a.dataset}: {a.message}")
    summary = investment_team_summary(profiles, features, alerts)
    with open("onboarding_report.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print("Wrote onboarding_report.json")
    print("Top by notional:",
          [(t["security_id"], t["notional"])
           for t in summary["top_by_notional"]])


if __name__ == "__main__":
    main()
