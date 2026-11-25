import pytest

from edgeprimitives.store import DurableStore, StoreError


@pytest.fixture
def store():
    s = DurableStore()
    yield s
    s.close()


def test_migrations_apply_in_order(store):
    assert store.schema_version == 3


def test_create_user_and_events(store):
    uid = store.create_user("ada@example.com", "Ada")
    assert uid == 1
    eid = store.record_event(uid, "signup", '{"plan": "free"}')
    assert eid == 1
    events = store.user_events(uid)
    assert len(events) == 1 and events[0]["kind"] == "signup"


def test_duplicate_email_rejected(store):
    store.create_user("ada@example.com", "Ada")
    with pytest.raises(StoreError):
        store.execute(
            "INSERT INTO users (email, name, created_at) VALUES (?, ?, ?)",
            ("ada@example.com", "Ada2", 0.0),
        )


def test_parameterized_query_blocks_injection(store):
    store.create_user("ada@example.com", "Ada")
    rows = store.execute("SELECT * FROM users WHERE email = ?", ("ada@example.com' OR '1'='1",))
    assert rows == []


def test_transaction_rolls_back_on_error(store):
    store.create_user("ada@example.com", "Ada")
    with pytest.raises(StoreError):
        store.transaction([
            ("INSERT INTO users (email, name, created_at) VALUES (?, ?, ?)", ("grace@example.com", "Grace", 0.0)),
            ("INSERT INTO users (email, name, created_at) VALUES (?, ?, ?)", ("ada@example.com", "Dup", 0.0)),
        ])
    assert store.execute("SELECT * FROM users WHERE email = ?", ("grace@example.com",)) == []


def test_execute_many_and_counts(store):
    uid = store.create_user("ada@example.com", "Ada")
    n = store.execute_many(
        "INSERT INTO events (user_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
        [(uid, "click", "{}", 1.0), (uid, "click", "{}", 2.0), (uid, "view", "{}", 3.0)],
    )
    assert n == 3
    counts = {r["kind"]: r["n"] for r in store.event_counts_by_kind()}
    assert counts == {"click": 2, "view": 1}


def test_query_log_records_timing(store):
    store.execute("SELECT 1")
    assert len(store.query_log) == 1
    assert store.query_log[0]["ms"] >= 0
