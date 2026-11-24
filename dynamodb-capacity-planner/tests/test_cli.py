from capplanner.cli import main


def test_cli_forecast(capsys):
    assert main(["forecast", "--hours", "336", "--ahead", "6"]) == 0
    assert "peak forecast" in capsys.readouterr().out


def test_cli_plan(capsys):
    assert main(["plan", "--reads", "1200", "--writes", "400",
                 "--item-kb", "2", "--storage-gb", "40"]) == 0
    out = capsys.readouterr().out
    assert "partitions" in out
    assert "headroom" in out


def test_cli_enforce(capsys):
    assert main(["enforce", "--customer", "customer-a", "--requests", "100",
                 "--request-rate", "150"]) == 0
    out = capsys.readouterr().out
    assert "admitted" in out
    assert "limit increase" in out


def test_cli_simulate(capsys):
    assert main(["simulate", "--partitions", "2"]) == 0
    out = capsys.readouterr().out
    assert "Fleet event simulation" in out
    assert "event ready" in out
