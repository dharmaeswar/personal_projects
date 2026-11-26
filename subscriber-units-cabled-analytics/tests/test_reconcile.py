from datetime import date

from uc_analytics import reconcile, seed

DATA = seed.generate()


def test_reconcile_finds_the_three_seeded_breaks():
    breaks = reconcile.reconcile(DATA["actuals"], DATA["salesforce"],
                                 DATA["deployment"], DATA["billing"])
    cats = [b["category"] for b in breaks]
    assert cats.count("missing_in_billing") == 7  # DAC-203, Aug 3-9
    assert cats.count("salesforce_mismatch") == 2  # PHL-102, Sep 14-15
    assert cats.count("deployment_mismatch") == 1  # ENG-303, Oct 5
    assert len(breaks) == 10


def test_seeded_break_values_are_exact():
    breaks = reconcile.reconcile(DATA["actuals"], DATA["salesforce"],
                                 DATA["deployment"], DATA["billing"])
    sf = [b for b in breaks if b["category"] == "salesforce_mismatch"]
    assert all(b["difference"] == -118 for b in sf)
    dep = [b for b in breaks if b["category"] == "deployment_mismatch"][0]
    assert dep["date"] == date(2026, 10, 5) and dep["difference"] == 210


def test_clean_feeds_produce_no_breaks():
    assert reconcile.reconcile(DATA["actuals"], DATA["actuals"],
                               DATA["actuals"], DATA["actuals"]) == []


def test_summarize_counts_by_category():
    breaks = reconcile.reconcile(DATA["actuals"], DATA["salesforce"],
                                 DATA["deployment"], DATA["billing"])
    s = reconcile.summarize(breaks)
    assert s["total"] == 10
    assert s["by_source"]["billing"] == 7
