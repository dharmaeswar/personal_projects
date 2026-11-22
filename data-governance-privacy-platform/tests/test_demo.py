"""End-to-end determinism tests: same seed -> same report."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_governance import run_demo  # noqa: E402


def test_demo_report_is_deterministic():
    first = run_demo()
    second = run_demo()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_demo_counts():
    report = run_demo()
    assert report["datasets"] == 4
    assert report["columns_classified"] == 29
    assert report["access_requests"]["total"] == 8
    assert report["access_requests"]["allowed"] == 4
    assert report["access_requests"]["denied"] == 4
    assert report["retention"]["actions"] == {
        "retain": 2, "delete-candidate": 1, "held": 1,
    }
    assert report["erasure"]["erased_total"] == 4
    assert report["erasure"]["held_datasets"] == ["loan_applications"]


def test_demo_classifies_planted_pii():
    report = run_demo()
    members = report["classifications"]["members"]
    assert members["ssn"]["sensitivity"] == "restricted"
    assert members["account_number"]["sensitivity"] == "restricted"
    assert members["email"]["sensitivity"] == "confidential"
    assert members["full_name"]["sensitivity"] == "confidential"
    assert members["state"]["sensitivity"] == "internal"
    loans = report["classifications"]["loan_applications"]
    assert loans["street_address"]["sensitivity"] == "confidential"
    assert loans["credit_score"]["sensitivity"] == "confidential"
