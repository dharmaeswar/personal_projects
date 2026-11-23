from fintech_agents.ledger import (
    BankLine, LedgerEntry, Reconciler, variance)


def test_exact_match():
    r = Reconciler()
    out = r.reconcile(
        [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03")],
        [BankLine("b1", "INV-1", 1000, "2026-11-03")])
    assert len(out.matches) == 1 and out.matches[0].rule == "exact"
    assert out.match_rate == 1.0


def test_amount_date_match_within_tolerance():
    r = Reconciler(date_tolerance_days=3)
    out = r.reconcile(
        [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03")],
        [BankLine("b1", "INV-1", 1000, "2026-11-05")])
    assert len(out.matches) == 1 and out.matches[0].rule == "amount_date"


def test_date_outside_tolerance_is_a_break():
    r = Reconciler(date_tolerance_days=3)
    out = r.reconcile(
        [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03")],
        [BankLine("b1", "INV-1", 1000, "2026-11-10")])
    assert len(out.matches) == 0
    assert len(out.unmatched_ledger) == 1


def test_same_reference_different_amount_is_mismatch():
    r = Reconciler()
    out = r.reconcile(
        [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03")],
        [BankLine("b1", "INV-1", 1200, "2026-11-03")])
    assert len(out.mismatches) == 1
    assert out.matches == []


def test_unmatched_both_sides_reported():
    r = Reconciler()
    out = r.reconcile(
        [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03"),
         LedgerEntry("e2", "AP", "INV-2", 2000, "2026-11-04")],
        [BankLine("b1", "INV-1", 1000, "2026-11-03"),
         BankLine("b9", "INV-9", 9000, "2026-11-04")])
    assert len(out.matches) == 1
    assert [e.entry_id for e in out.unmatched_ledger] == ["e2"]
    assert [ln.line_id for ln in out.unmatched_bank] == ["b9"]


def test_variance_math():
    v = variance(1_125_000, 1_000_000)
    assert v["variance_minor"] == 125_000
    assert v["variance_pct"] == 12.5
    assert variance(1_000_000, 1_000_000)["variance_pct"] == 0.0
    assert variance(900_000, 1_000_000)["variance_pct"] == -10.0
