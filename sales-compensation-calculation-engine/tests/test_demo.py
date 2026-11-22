"""End-to-end demo: seeded run produces a consistent report."""
import json

from run_comp import run


def test_demo_run_is_consistent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    summary = run()
    assert summary["reps"] == 3
    assert summary["deals"] == 5
    assert summary["results"] == 5  # D1001, D1002 x2 reps, D1003, D1005
    assert summary["plan_versions"] == 2
    assert summary["audit_chain_ok"] is True
    assert summary["findings"] == []
    # Net commission: R1 420000*8% + 304000*8% = 57920; R3 76000*8% + 210000*8% + 1500 spiff
    # = 6080 + 16800 + 1500 = 24380; R2 150000*6% - 7200 clawback = 1800.
    assert summary["total_net"] == "84100.00"
    assert summary["payments"] == 3


def test_demo_writes_report_files(tmp_path, monkeypatch):
    import run_comp
    monkeypatch.chdir(tmp_path)
    run_comp.main()
    assert (tmp_path / "comp_report.txt").exists()
    assert (tmp_path / "comp_report.json").exists()
    data = json.loads((tmp_path / "comp_report.json").read_text())
    assert data["audit_chain_ok"] is True
    assert data["findings"] == []
