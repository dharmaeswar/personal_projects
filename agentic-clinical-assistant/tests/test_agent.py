from clinical_agent.agent import MAX_STEPS, Agent
from clinical_agent.evals import run_evals
from clinical_agent.phi import contains_phi


def test_follow_up_uses_search_and_patient_context():
    result = Agent().run(
        "When should this patient come back for diabetes follow-up?",
        patient_id="P-1001",
    )
    assert "search_kb" in result["tools_used"]
    assert "get_patient_context" in result["tools_used"]
    assert "Diabetes follow-up" in result["answer"]
    assert result["escalated"] is False
    assert result["sent"] is False


def test_urgent_symptoms_held_without_approval():
    result = Agent().run(
        "The patient reports chest pain and feeling breathless.",
        patient_id="P-1001",
    )
    assert result["pending_approval"] is True
    assert result["escalated"] is False
    assert "held for clinician approval" in result["answer"]


def test_urgent_symptoms_escalate_with_approval():
    result = Agent().run(
        "The patient reports chest pain and feeling breathless.",
        patient_id="P-1001",
        approve_send=True,
    )
    assert result["escalated"] is True
    assert "Escalated to the on-call clinician" in result["answer"]


def test_summary_request_drafts_for_review():
    result = Agent().run(
        "Draft a summary of this patient's diabetes care.", patient_id="P-1003"
    )
    assert "draft_summary" in result["tools_used"]
    assert "Draft summary ready" in result["answer"]
    assert result["sent"] is False


def test_step_budget_is_never_exceeded():
    result = Agent().run(
        "Send this patient a message and escalate a referral for a summary.",
        patient_id="P-1002",
    )
    assert len(result["tools_used"]) <= MAX_STEPS


def test_audit_log_never_contains_phi():
    result = Agent().run(
        "Alice Johnson reports chest pain, MRN-482913, call 716-555-0142.",
        patient_id="P-1001",
    )
    assert result["audit"]
    for entry in result["audit"]:
        assert not contains_phi(entry["detail"]), entry


def test_unknown_patient_is_reported_not_crash():
    result = Agent().run("Review this patient.", patient_id="P-9999")
    assert "search_kb" in result["tools_used"]
    assert "Could not run get_patient_context" in result["answer"]


def test_all_eval_cases_pass():
    results = run_evals()
    assert len(results) == 6
    failed = [r for r in results if not r["passed"]]
    assert failed == []
