import time

import pytest

from edgeprimitives.kv import KeyValueStore, KVError


@pytest.fixture
def kv():
    k = KeyValueStore()
    yield k
    k.close()


def test_put_get_roundtrip(kv):
    kv.put("user:1", "ada")
    assert kv.get("user:1") == "ada"


def test_put_overwrites(kv):
    kv.put("k", "v1")
    kv.put("k", "v2")
    assert kv.get("k") == "v2"


def test_missing_key_returns_none(kv):
    assert kv.get("nope") is None


def test_empty_key_rejected(kv):
    with pytest.raises(KVError):
        kv.put("", "v")


def test_ttl_expires(kv):
    kv.put("temp", "x", ttl_s=0.05)
    assert kv.get("temp") == "x"
    time.sleep(0.1)
    assert kv.get("temp") is None
    assert kv.purge_expired() == 1


def test_metadata_roundtrip(kv):
    kv.put("doc:1", "body", metadata={"version": 3})
    got = kv.get_with_metadata("doc:1")
    assert got["value"] == "body" and got["metadata"] == {"version": 3}


def test_delete(kv):
    kv.put("k", "v")
    assert kv.delete("k") is True
    assert kv.delete("k") is False
    assert kv.get("k") is None


def test_list_prefix_and_pagination(kv):
    for i in range(5):
        kv.put(f"user:{i}", str(i))
    kv.put("other:1", "x")
    page1 = kv.list_keys(prefix="user:", limit=2)
    assert page1["keys"] == ["user:0", "user:1"]
    assert page1["next_cursor"] == "user:1"
    page2 = kv.list_keys(prefix="user:", limit=2, cursor=page1["next_cursor"])
    assert page2["keys"] == ["user:2", "user:3"]
    page3 = kv.list_keys(prefix="user:", limit=2, cursor=page2["next_cursor"])
    assert page3["keys"] == ["user:4"] and page3["next_cursor"] is None


def test_replica_lag_returns_stale_then_fresh():
    kv_lag = KeyValueStore(replica_lag_s=60)
    try:
        kv_lag.put("k", "v1")
        assert kv_lag.get("k", replica=True) is None  # not replicated yet
        assert kv_lag.get("k") == "v1"  # primary is current
    finally:
        kv_lag.close()


def test_replica_zero_lag_is_current():
    kv_fast = KeyValueStore(replica_lag_s=0)
    try:
        kv_fast.put("k", "v1")
        assert kv_fast.get("k", replica=True) == "v1"
    finally:
        kv_fast.close()
