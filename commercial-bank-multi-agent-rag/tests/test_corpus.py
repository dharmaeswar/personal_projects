from bank_rag.corpus import BORROWERS, build_corpus


def test_three_borrowers_nine_docs():
    docs = build_corpus()
    assert len(docs) == 9
    assert {d["borrower"] for d in docs} == set(BORROWERS)
    assert {d["kind"] for d in docs} == {"financials", "memo", "covenant"}


def test_figures_are_positive_and_consistent():
    for name, figures in BORROWERS.items():
        assert figures["revenue"] > figures["ebitda"] > 0
        assert figures["total_debt"] > 0
        assert figures["interest_expense"] > 0
        assert figures["max_leverage"] > 0
        assert figures["min_interest_coverage"] > 0


def test_blue_rock_breaches_its_leverage_covenant():
    figures = BORROWERS["BlueRock Packaging Co"]
    leverage = figures["total_debt"] / figures["ebitda"]
    assert leverage == 4.0
    assert leverage > figures["max_leverage"]


def test_northgate_is_inside_its_covenants():
    figures = BORROWERS["Northgate Logistics Group"]
    assert figures["total_debt"] / figures["ebitda"] <= figures["max_leverage"]
    assert figures["ebitda"] / figures["interest_expense"] >= figures["min_interest_coverage"]
