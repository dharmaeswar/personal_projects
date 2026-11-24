from airload.cli import main


def test_plan_command_succeeds(capsys):
    assert main(["plan", "--flight", "AMZ101"]) == 0
    out = capsys.readouterr().out
    assert "LOAD SHEET" in out
    assert "WITHIN" in out


def test_verify_command_passes(capsys):
    assert main(["verify", "--flight", "AMZ101"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_verify_tamper_command_fails(capsys):
    assert main(["verify", "--flight", "AMZ101", "--tamper"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_scales_command_reconciles(capsys):
    assert main(["scales", "--flight", "AMZ101"]) == 0
    assert "reconcile within tolerance" in capsys.readouterr().out


def test_simulate_command_fans_out(capsys):
    assert main(["simulate", "--flight", "AMZ101"]) == 0
    out = capsys.readouterr().out
    assert "1 message(s) delivered" in out
    assert "0 dead-lettered" in out
