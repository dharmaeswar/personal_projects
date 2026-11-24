"""Run the full compliance model risk validation on synthetic data.

Prints the validation report and writes validation_report.txt.
"""

from sklearn.model_selection import train_test_split

from compliance_model_risk import (
    generate_alert_book,
    generate_monitoring_book,
    train_benchmark,
    train_challenger,
    train_champion,
)
from compliance_model_risk.governance import ComplianceModel, ModelInventory
from compliance_model_risk.report import build_report, render_text


def main():
    book = generate_alert_book(n=6000, seed=42)
    train, test = train_test_split(
        book, test_size=0.3, random_state=42, stratify=book["sar_worthy"]
    )
    later = generate_monitoring_book(n=6000, seed=7, drift=0.15)

    champion = train_champion(train)
    challenger = train_challenger(train)
    benchmark = train_benchmark(train)

    inventory = ModelInventory()
    inventory.add(
        ComplianceModel(
            "AML-TM-01",
            "Transaction Monitoring Alert Model",
            "AML alert triage",
            "High",
            owner="Compliance Analytics",
            stage="In Use",
            days_since_validation=400,
            open_high_findings=1,
        )
    )
    inventory.add(
        ComplianceModel(
            "FL-02",
            "Fair Lending Pricing Model",
            "Credit pricing",
            "High",
            owner="",
            stage="Validation",
            days_since_validation=120,
        )
    )
    inventory.add(
        ComplianceModel(
            "CDD-03",
            "Customer Due Diligence Scoring",
            "Onboarding risk scoring",
            "Medium",
            owner="Financial Crime Ops",
            stage="In Use",
            days_since_validation=200,
        )
    )

    report = build_report(train, test, later, champion, challenger, benchmark, inventory)
    text = render_text(report)
    print(text)
    with open("validation_report.txt", "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
