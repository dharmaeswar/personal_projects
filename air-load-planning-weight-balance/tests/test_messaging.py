import pytest

from airload.messaging import Queue, Topic, decode_event, encode_event


def test_topic_fans_out_to_every_subscriber():
    topic = Topic("load-plan-events")
    ops = Queue("ops")
    audit = Queue("audit")
    topic.subscribe(ops)
    topic.subscribe(audit)
    topic.publish("load_plan.finalized", {"flight": "AMZ101"})
    assert ops.pending_count == 1
    assert audit.pending_count == 1


def test_receive_acknowledge_clears_the_message():
    queue = Queue("ops")
    msg = queue.enqueue({"flight": "AMZ101"})
    received = queue.receive()
    assert received is not None
    assert received.message_id == msg.message_id
    queue.acknowledge(msg.message_id)
    assert queue.pending_count == 0
    assert queue.receive() is None


def test_failed_message_is_redelivered_until_max_receives():
    queue = Queue("ops", max_receives=3)
    msg = queue.enqueue({"flight": "AMZ101"})
    for _ in range(2):
        received = queue.receive()
        assert received is not None
        queue.fail(received.message_id)
    assert queue.pending_count == 1
    assert queue.dead_letter_count == 0


def test_message_moves_to_dead_letter_after_max_receives():
    queue = Queue("ops", max_receives=2)
    queue.enqueue({"flight": "AMZ101"})
    for _ in range(2):
        received = queue.receive()
        assert received is not None
        queue.fail(received.message_id)
    assert queue.pending_count == 0
    assert queue.dead_letter_count == 1
    assert queue.dead_letter[0].receives == 2


def test_failing_unknown_message_raises():
    queue = Queue("ops")
    with pytest.raises(KeyError):
        queue.fail("no-such-id")


def test_subscribing_twice_does_not_duplicate():
    topic = Topic("load-plan-events")
    queue = Queue("ops")
    topic.subscribe(queue)
    topic.subscribe(queue)
    topic.publish("load_plan.finalized", {"flight": "AMZ101"})
    assert queue.pending_count == 1


def test_event_encoding_round_trip():
    body = {"event_type": "load_plan.finalized", "payload": {"flight": "AMZ101"}}
    assert decode_event(encode_event(body)) == body
