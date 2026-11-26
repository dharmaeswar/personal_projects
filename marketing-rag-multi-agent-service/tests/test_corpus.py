from marketing_rag.corpus import (CAMPAIGNS, CONTENT_ASSETS, SEGMENTS,
                                  build_documents, campaign_text,
                                  generate_contacts, segment_text)


def test_corpus_sizes():
    assert len(CAMPAIGNS) == 8
    assert len(SEGMENTS) == 6
    assert len(CONTENT_ASSETS) == 10
    assert len(build_documents()) == 24


def test_campaign_text_carries_cpa_and_roi():
    text = campaign_text(CAMPAIGNS[0])  # CMP-001: 42000/296, 148000/42000
    assert "Cost per acquisition $141.89" in text
    assert "Return on spend 3.52x" in text


def test_contacts_deterministic():
    first = generate_contacts()
    second = generate_contacts()
    assert len(first) == 200
    assert first == second
    assert all(c["segment_id"].startswith("SEG-") for c in first)
    assert all(c["id"].startswith("CON-") for c in first)


def test_segment_text_has_size_and_source():
    text = segment_text(SEGMENTS[0])
    assert "18400" in text
    assert "CRM" in text
