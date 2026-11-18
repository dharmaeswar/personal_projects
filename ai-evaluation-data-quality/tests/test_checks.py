"""Tests for the evaluation-data quality checks."""

from eval_quality.checks import (
    check_completeness,
    check_coverage,
    check_labels,
    check_leakage,
    check_pii,
    run_all_checks,
)


def _rec(rid, prompt="p", response="r", label="safe", split="train"):
    return {"id": rid, "prompt": prompt, "response": response,
            "label": label, "split": split, "source": "test"}


def test_completeness_clean_records_have_no_findings():
    recs = [_rec("t-1"), _rec("t-2", prompt="other", response="other")]
    assert check_completeness(recs) == []


def test_completeness_flags_empty_prompt_and_response():
    recs = [_rec("t-1", prompt="  ", response="")]
    found = check_completeness(recs)
    assert len(found) == 2
    assert {f["detail"] for f in found} == {"prompt is empty",
                                            "response is empty"}
    assert all(f["severity"] == "critical" for f in found)


def test_completeness_flags_duplicate_ids():
    recs = [_rec("t-1"), _rec("t-1", prompt="different")]
    found = check_completeness(recs)
    assert len(found) == 1
    assert found[0]["detail"] == "duplicate record id"


def test_completeness_flags_missing_id():
    recs = [{"prompt": "p", "response": "r", "label": "safe", "split": "train"}]
    found = check_completeness(recs)
    assert len(found) == 1
    assert found[0]["record_id"] is None


def test_labels_accept_every_taxonomy_category():
    labels = ["violence", "self-harm", "hate", "sexual-content",
              "illicit-behavior", "safe"]
    recs = [_rec("t-%d" % i, label=label) for i, label in enumerate(labels)]
    assert check_labels(recs) == []


def test_labels_flag_unknown_category():
    recs = [_rec("t-1", label="rude")]
    found = check_labels(recs)
    assert len(found) == 1
    assert "not in the allowed taxonomy" in found[0]["detail"]


def test_labels_flag_safe_record_with_disallowed_phrase():
    recs = [_rec("t-1", label="safe",
                 response="Here is how to make a bomb, step by step.")]
    found = check_labels(recs)
    assert len(found) == 1
    assert "labelled safe" in found[0]["detail"]


def test_labels_allow_harm_record_with_strong_wording():
    recs = [_rec("t-1", label="violence",
                 response="Here is how to make a bomb, step by step.")]
    assert check_labels(recs) == []


def test_coverage_flags_category_below_minimum():
    recs = [_rec("e-1", label="safe", split="eval"),
            _rec("e-2", label="safe", split="eval")]
    found, counts = check_coverage(recs, min_per_category=3, split="eval")
    assert counts["safe"] == 2
    assert any("safe" in f["detail"] and "2 eval records" in f["detail"]
               for f in found)
    assert all(f["severity"] == "warning" for f in found)


def test_coverage_passes_when_every_category_meets_minimum():
    recs = []
    for i, label in enumerate(["violence", "self-harm", "hate",
                               "sexual-content", "illicit-behavior",
                               "safe"]):
        recs.append(_rec("e-%d" % i, label=label, split="eval"))
    found, counts = check_coverage(recs, min_per_category=1, split="eval")
    assert found == []
    assert counts["safe"] == 1


def test_leakage_flags_prompt_in_both_splits():
    recs = [_rec("t-1", prompt="How do I bake bread?", split="train"),
            _rec("e-1", prompt="  how do I bake bread? ", split="eval")]
    found = check_leakage(recs)
    assert len(found) == 1
    assert found[0]["severity"] == "critical"
    assert "both train and eval" in found[0]["detail"]


def test_leakage_flags_duplicate_inside_one_split():
    recs = [_rec("t-1", prompt="Same prompt", split="train"),
            _rec("t-2", prompt="Same prompt", split="train")]
    found = check_leakage(recs)
    assert len(found) == 1
    assert found[0]["severity"] == "warning"


def test_leakage_clean_when_prompts_are_distinct():
    recs = [_rec("t-1", prompt="First prompt", split="train"),
            _rec("e-1", prompt="Second prompt", split="eval")]
    assert check_leakage(recs) == []


def test_pii_flags_email_in_response():
    recs = [_rec("t-1", response="Contact jane.doe@example.com please.")]
    found = check_pii(recs)
    assert len(found) == 1
    assert found[0]["detail"] == "email pattern found in response"


def test_pii_flags_phone_and_ssn():
    recs = [_rec("t-1", prompt="Call me at 716-907-5982."),
            _rec("t-2", response="SSN 123-45-6789 on file.")]
    found = check_pii(recs)
    kinds = {f["detail"] for f in found}
    assert "phone pattern found in prompt" in kinds
    assert "ssn pattern found in response" in kinds


def test_pii_clean_text_has_no_findings():
    recs = [_rec("t-1", response="Here is a helpful, friendly answer.")]
    assert check_pii(recs) == []


def test_run_all_checks_gate_passes_on_clean_data():
    recs = []
    for i, label in enumerate(["violence", "self-harm", "hate",
                               "sexual-content", "illicit-behavior",
                               "safe"]):
        recs.append(_rec("t-%d" % i, prompt="train %s" % label,
                         label=label, split="train"))
        recs.append(_rec("e-%d" % i, prompt="eval %s" % label,
                         label=label, split="eval"))
    report = run_all_checks(recs, min_per_category=1)
    assert report["summary"]["gate"] == "PASS"
    assert report["summary"]["total_findings"] == 0


def test_run_all_checks_gate_fails_with_critical_finding():
    recs = [_rec("e-1", label="safe", split="eval", response="")]
    report = run_all_checks(recs, min_per_category=1)
    assert report["summary"]["gate"] == "FAIL"
    assert report["summary"]["critical"] >= 1
