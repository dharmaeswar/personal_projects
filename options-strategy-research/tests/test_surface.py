from options.data import build_chain
from options.surface import run_all_checks


def test_clean_chain_has_no_arbitrage_breaks():
    chain = build_chain(100.0)
    surface, breaks = run_all_checks(chain)
    assert breaks == []
    assert sorted(surface) == [30, 60, 90]


def test_surface_recovers_smile_vol():
    chain = build_chain(100.0)
    surface, _ = run_all_checks(chain)
    atm = [q for q in surface[30] if q["strike"] == 100.0 and q["kind"] == "call"][0]
    wing = [q for q in surface[30] if q["strike"] == 85.0 and q["kind"] == "call"][0]
    assert abs(atm["implied_vol"] - 0.25) < 0.01
    assert wing["implied_vol"] > atm["implied_vol"]  # smile: wings above ATM


def test_monotonicity_break_detected():
    chain = build_chain(100.0)
    # Break the surface: raise the 105 call above the 100 call.
    for q in chain:
        if q["kind"] == "call" and q["strike"] == 105.0 and q["expiry_days"] == 30:
            q["mid"] = 99.0
    _, breaks = run_all_checks(chain)
    assert any(b["check"] == "call_monotonicity" for b in breaks)


def test_butterfly_break_detected():
    chain = build_chain(100.0)
    # Break the butterfly: push the middle strike call far above its neighbours.
    for q in chain:
        if q["kind"] == "call" and q["strike"] == 100.0 and q["expiry_days"] == 30:
            q["mid"] = 50.0
    _, breaks = run_all_checks(chain)
    assert any(b["check"] == "butterfly" for b in breaks)


def test_calendar_break_detected():
    chain = build_chain(100.0)
    # Break calendar arbitrage: make the 90d ATM vol far lower than the 30d one.
    # Mid 1.50 sits just above the discounted intrinsic value (~1.23), so
    # it implies a tiny vol and a total variance below the 30d expiry's.
    for q in chain:
        if q["expiry_days"] == 90 and q["strike"] == 100.0:
            q["mid"] = 1.50
    _, breaks = run_all_checks(chain)
    assert any(b["check"] == "calendar" for b in breaks)
