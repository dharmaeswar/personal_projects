from subscription_billing.events import Event, EventBus, Queue


def make_event(eid, key="cust-1", dedup=None):
    return Event(eid, "billing.charge", "partner-a", key,
                 {"subscription_id": "sub-1"}, dedup_id=dedup or eid)


def test_fanout_delivers_to_every_subscribed_queue():
    bus = EventBus()
    q1, q2 = Queue("billing"), Queue("audit")
    bus.subscribe("billing.charge", q1)
    bus.subscribe("billing.charge", q2)
    assert bus.publish("billing.charge", make_event("e1")) == {
        "billing": True, "audit": True}
    assert q1.depth() == 1 and q2.depth() == 1


def test_duplicate_dedup_id_is_rejected():
    q = Queue("billing")
    assert q.enqueue(make_event("e1", dedup="d1")) is True
    assert q.enqueue(make_event("e2", dedup="d1")) is False
    assert q.depth() == 1


def test_fifo_per_grouping_key_blocks_later_event_until_first_done():
    q = Queue("billing")
    q.enqueue(make_event("e1"))
    q.enqueue(make_event("e2"))
    first = q.receive(now=0.0)
    assert first.event_id == "e1"
    assert q.receive(now=0.0) is None  # e1 still in flight
    assert q.delete(first) is True
    second = q.receive(now=0.0)
    assert second.event_id == "e2"


def test_different_keys_deliver_independently():
    q = Queue("billing")
    q.enqueue(make_event("e1", key="cust-1"))
    q.enqueue(make_event("e2", key="cust-2"))
    assert q.receive(now=0.0).event_id == "e1"
    assert q.receive(now=0.0).event_id == "e2"


def test_message_goes_to_dlq_after_max_receives():
    q = Queue("billing", max_receives=1, visibility_timeout_s=0.0)
    q.enqueue(make_event("e1"))
    assert q.receive(now=0.0).event_id == "e1"
    assert q.receive(now=0.0) is None  # exceeded max receives -> DLQ
    assert q.dlq_depth() == 1
    assert q.depth() == 0


def test_delete_removes_and_unblocks_key():
    q = Queue("billing")
    q.enqueue(make_event("e1"))
    got = q.receive(now=0.0)
    assert q.delete(got) is True
    assert q.depth() == 0
    assert q.delete(got) is False
