import pytest

from perf.nav import NavPeriod, roll_forward, reconcile, chain_roll_forward


def _period():
    return NavPeriod(beginning_nav=1000.0, contributions=200.0,
                     distributions=50.0, income=30.0, gains=40.0,
                     ending_nav=1220.0)


def test_roll_forward_exact():
    assert roll_forward(_period()) == 1220.0


def test_reconcile_clean_ledger():
    residual, ok = reconcile(_period())
    assert residual == 0.0 and ok is True


def test_reconcile_flags_plug():
    broken = NavPeriod(beginning_nav=1000.0, contributions=200.0,
                       distributions=50.0, income=30.0, gains=40.0,
                       ending_nav=1225.0)
    residual, ok = reconcile(broken)
    assert residual == 5.0 and ok is False


def test_chain_roll_forward_links_periods():
    p1 = _period()
    p2 = NavPeriod(beginning_nav=1220.0, contributions=0.0, distributions=100.0,
                   income=20.0, gains=60.0, ending_nav=1200.0)
    assert chain_roll_forward([p1, p2]) == 1200.0


def test_chain_roll_forward_rejects_nav_break():
    p1 = _period()
    p2 = NavPeriod(beginning_nav=999.0, contributions=0.0, distributions=0.0,
                   income=0.0, gains=0.0, ending_nav=999.0)
    with pytest.raises(ValueError):
        chain_roll_forward([p1, p2])


def test_chain_roll_forward_rejects_unreconciled_period():
    broken = NavPeriod(beginning_nav=1000.0, contributions=200.0,
                       distributions=50.0, income=30.0, gains=40.0,
                       ending_nav=1300.0)
    with pytest.raises(ValueError):
        chain_roll_forward([broken])
