from clinical_agent.retrieval import search


def test_diabetes_query_returns_follow_up_doc_first():
    hits = search("When should this patient come back for diabetes follow-up?")
    assert hits
    assert hits[0][0]["doc_id"] == "KB-001"


def test_hypertension_query_returns_medication_review():
    hits = search("Review this patient's blood pressure medication.")
    assert hits
    assert hits[0][0]["doc_id"] == "KB-002"


def test_urgent_symptoms_query_returns_discharge_doc():
    hits = search("patient reports chest pain and shortness of breath")
    assert hits
    assert hits[0][0]["doc_id"] == "KB-003"


def test_unknown_query_returns_nothing():
    assert search("quantum chromodynamics lattice gauge") == []


def test_empty_query_returns_nothing():
    assert search("") == []


def test_top_k_is_respected():
    hits = search("medication", top_k=1)
    assert len(hits) == 1


def test_scores_are_positive_and_sorted():
    hits = search("medication adherence review")
    scores = [score for _, score in hits]
    assert all(score > 0 for score in scores)
    assert scores == sorted(scores, reverse=True)
