import pytest

from edgeprimitives.queue import MessageQueue, QueueError


@pytest.fixture
def queue():
    q = MessageQueue(max_attempts=3)
    yield q
    q.close()


def test_enqueue_and_lease_fifo(queue):
    ids = queue.enqueue_many([{"n": 1}, {"n": 2}, {"n": 3}])
    assert ids == [1, 2, 3]
    leased = queue.lease(batch_size=2)
    assert [m["body"]["n"] for m in leased] == [1, 2]
    assert queue.depth() == 3  # leased rows stay until acked


def test_lease_hides_until_visibility_timeout(queue):
    queue.enqueue({"n": 1})
    assert len(queue.lease(batch_size=10, visibility_timeout_s=60)) == 1
    assert queue.lease(batch_size=10) == []  # still hidden


def test_ack_removes_message(queue):
    mid = queue.enqueue({"n": 1})
    queue.ack(mid)
    assert queue.depth() == 0
    assert queue.lease() == []


def test_nack_retries_then_dead_letters(queue):
    mid = queue.enqueue({"n": 1})
    queue.lease()
    assert queue.nack(mid, "boom") == "retried"
    assert queue.depth() == 1
    queue.lease()
    assert queue.nack(mid, "boom") == "retried"
    queue.lease()
    assert queue.nack(mid, "boom") == "dead-lettered"
    assert queue.depth() == 0
    assert queue.dead_letter_count() == 1
    dl = queue.dead_letters()[0]
    assert dl["body"] == {"n": 1} and dl["reason"] == "boom"


def test_nack_unknown_message_raises(queue):
    with pytest.raises(QueueError):
        queue.nack(999, "gone")


def test_batch_lease_limit(queue):
    queue.enqueue_many([{"n": i} for i in range(5)])
    assert len(queue.lease(batch_size=2)) == 2
    assert len(queue.lease(batch_size=10)) == 3
