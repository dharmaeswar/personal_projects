from prediction_markets.ingest import generate_feed
from prediction_markets.stream import Consumer, Topic


def test_stream_delivers_all_once():
    feed = generate_feed()
    topic = Topic("sports-odds")
    for snap in feed:
        topic.produce(snap)
    consumer = Consumer(topic, group="research")
    first = consumer.poll()
    # 866 produced rows, 2 exact duplicates deduped by key.
    assert len(first) == 864
    assert consumer.poll() == []  # offsets committed; nothing new


def test_stream_replay_is_exactly_once_effect():
    feed = generate_feed()
    topic = Topic("sports-odds")
    for snap in feed:
        topic.produce(snap)
    consumer = Consumer(topic, group="research")
    consumer.poll()
    replayed = consumer.replay_from(0)
    assert replayed == []  # every key already seen
    assert len(consumer.delivered) == 864


def test_stream_offsets_advance():
    topic = Topic("t")
    feed = generate_feed()[:5]
    for snap in feed:
        topic.produce(snap)
    consumer = Consumer(topic, group="g")
    consumer.poll()
    assert consumer.committed_offset == 5
