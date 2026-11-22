import pytest

from investment_governance import governance as gov


def _record(**over):
    base = dict(
        model_id="T-01", name="Test model", model_type="risk_var",
        owner="Risk Analytics", stage="in_use", risk_tier="high",
        months_since_validation=6,
    )
    base.update(over)
    return gov.ModelRecord(**base)


def test_validation_due_high_tier():
    assert gov.validation_due(_record(months_since_validation=13)) is True
    assert gov.validation_due(_record(months_since_validation=12)) is False


def test_validation_due_cadence_by_tier():
    assert gov.validation_due(_record(risk_tier="low", months_since_validation=25)) is True
    assert gov.validation_due(_record(risk_tier="low", months_since_validation=24)) is False
    assert gov.validation_due(_record(risk_tier="medium", months_since_validation=19)) is True


def test_inventory_gaps_overdue():
    gaps = gov.inventory_gaps([_record(months_since_validation=20)])
    assert len(gaps) == 1
    assert "overdue" in gaps[0]


def test_inventory_gaps_missing_owner():
    gaps = gov.inventory_gaps([_record(owner="")])
    assert any("no accountable owner" in g for g in gaps)


def test_inventory_gaps_high_finding_in_use():
    rec = _record(findings=[gov.Finding("Bad data", "High", "Inputs unchecked")])
    gaps = gov.inventory_gaps([rec])
    assert any("open High finding" in g for g in gaps)


def test_inventory_gaps_clean_register():
    assert gov.inventory_gaps([_record()]) == []


def test_finding_bad_severity_raises():
    with pytest.raises(ValueError):
        gov.Finding("x", "Critical", "y")


def test_record_bad_stage_raises():
    with pytest.raises(ValueError):
        _record(stage="deployed")


def test_validation_opinion():
    assert gov.validation_opinion([]) == "Satisfactory"
    assert gov.validation_opinion([gov.Finding("a", "Medium", "b")]) == "Needs Improvement"
    assert gov.validation_opinion([gov.Finding("a", "High", "b")]) == "Unsatisfactory"


def test_effective_challenge_checklist_covers_eight_items():
    items = gov.effective_challenge_checklist()
    assert len(items) == 8
    assert any("Conceptual soundness" in i for i in items)
    assert any("Ongoing monitoring" in i for i in items)


def test_build_validation_report():
    rec = _record(findings=[gov.Finding("Turnover undocumented", "Medium", "No cap in note.")])
    evidence = {c: True for c in gov.effective_challenge_checklist()}
    report = gov.build_validation_report(rec, rec.findings, evidence)
    assert report["opinion"] == "Needs Improvement"
    assert report["checklist_evidenced"] == 8
    assert report["checklist_missing"] == []
    assert report["findings"][0]["severity"] == "Medium"


def test_build_validation_report_missing_checklist():
    rec = _record()
    report = gov.build_validation_report(rec, [], {"Conceptual soundness: theory, assumptions and limitations documented": True})
    assert report["checklist_evidenced"] == 1
    assert len(report["checklist_missing"]) == 7
