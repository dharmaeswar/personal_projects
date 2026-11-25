"""Run the energy-data modelling pipeline end to end and print a report.

Usage: python run_energy_model.py
"""

import json

from eng_sim_evaluator.deployment import (
    deployment_checklist,
    export_model_artifact,
    predict_from_artifact,
)
from eng_sim_evaluator.energy_data import (
    DICTIONARY_VERSION,
    clean_and_validate,
    eda_summary,
    generate_drilling_data,
)
from eng_sim_evaluator.energy_model import (
    FEATURES,
    OlsModel,
    build_features,
    model_card,
    sensitivity_analysis,
    train_holdout_split,
    validate_models,
)


def main() -> None:
    raw = generate_drilling_data(n_rows=400, seed=7)
    print(f"Raw telemetry: {len(raw)} rows")
    cleaned, report = clean_and_validate(raw)
    print(f"Cleaned: {len(cleaned)} rows "
          f"({report['rows_dropped_total']} dropped: "
          f"{report['rows_dropped_missing']} missing, "
          f"{report['duplicate_rows']} duplicates, rest out of range)")

    eda = eda_summary(cleaned)
    print(f"EDA: {len(eda['anomalies_flagged'])} 3-sigma ROP anomalies flagged")

    validation = validate_models(cleaned, seed=7)
    print("\nHoldout metrics (MAE / RMSE / R2):")
    for name in ("ols", "random_forest", "naive_mean_baseline"):
        m = validation[name]
        print(f"  {name:20s} MAE {m['mae']:.2f}  RMSE {m['rmse']:.2f}  "
              f"R2 {m['r2']:.3f}")
    print(f"  analytic truth vs observed: "
          f"MAE {validation['analytic_truth_vs_observed']['mae']:.2f}")
    print(f"  OLS vs analytic truth: "
          f"MAE {validation['ols_vs_analytic_truth']['mae']:.2f}")

    featured = build_features(cleaned)
    train, _ = train_holdout_split(featured, seed=7)
    ols = OlsModel().fit(train[FEATURES].to_numpy(dtype=float),
                         train["rop_ft_hr"].to_numpy(dtype=float))
    print("\nSensitivity (+10% bump, mean predicted ROP change):")
    for row in sensitivity_analysis(ols, train[FEATURES].to_numpy(dtype=float)):
        print(f"  {row['feature']:18s} {row['mean_predicted_change_ft_hr']:+.2f} ft/hr")

    artifact = export_model_artifact(ols, validation, DICTIONARY_VERSION)
    sample = featured.iloc[0]
    print("\nDeployment artifact:", artifact["artifact_version"])
    print(f"  sample prediction from artifact: "
          f"{predict_from_artifact(artifact, sample.to_dict()):.2f} ft/hr "
          f"(observed {sample['rop_ft_hr']:.2f})")
    print("\nDeployment checklist:")
    for step in deployment_checklist():
        print(f"  {step['step']}. {step['action']} Gate: {step['gate']}")

    card = model_card(validation, report, DICTIONARY_VERSION)
    print("\nModel card limitations:")
    for item in card["limitations"]:
        print(f"  - {item}")
    print("\nFull validation JSON:")
    print(json.dumps(validation, indent=2)[:1200], "...")


if __name__ == "__main__":
    main()
