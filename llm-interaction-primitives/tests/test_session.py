"""Tests for session token counting and context compaction."""

from interaction_lib import Message, Session, SimpleTokenizer


def _session_with_history():
    tok = SimpleTokenizer()
    session = Session(tokenizer=tok)
    session.append(Message("system", "You are helpful."))
    session.append(Message("user", "First question here."))
    session.append(Message("assistant", "First answer here."))
    session.append(Message("user", "Second question here."))
    session.append(Message("assistant", "Second answer here."))
    return session


def test_token_count_sums_messages():
    session = _session_with_history()
    assert session.token_count() > 0


def test_compact_keeps_system_and_recent_turns():
    session = _session_with_history()
    dropped = session.compact(max_tokens=12)
    assert dropped >= 1
    assert session.messages[0].role == "system"
    assert session.messages[-1].content == "Second answer here."
    assert session.token_count() <= 12


def test_compact_with_generous_budget_drops_nothing():
    session = _session_with_history()
    assert session.compact(max_tokens=10000) == 0
    assert len(session.messages) == 5


def test_compact_never_drops_the_only_message():
    session = Session()
    session.append(Message("system", "You are helpful."))
    assert session.compact(max_tokens=1) == 0
    assert len(session.messages) == 1
