"""Market-data feed health checks (synthetic inputs only).

Checks a feed snapshot for staleness, missing sequence numbers, and
quote-rate drops against an expected baseline. No real feed is
contacted.
"""

STALE_SECONDS = 5
MIN_QUOTE_RATE_FRACTION = 0.8


def detect_sequence_gaps(received_seqs):
    """Return sorted list of missing sequence numbers in a run."""
    if not received_seqs:
        return []
    seqs = sorted(set(received_seqs))
    return [n for n in range(seqs[0], seqs[-1] + 1) if n not in set(seqs)]


def check_feed(feed):
    """Check one feed snapshot.

    feed: dict with keys ``name``, ``last_update_age_s``,
    ``received_seqs`` (list of ints), ``quotes_per_min`` and
    ``expected_quotes_per_min``.
    Returns a dict with ``status`` (ok/degraded/down), ``stale``,
    ``gaps`` and ``rate_ok``.
    """
    gaps = detect_sequence_gaps(feed.get("received_seqs", []))
    stale = feed.get("last_update_age_s", 0) > STALE_SECONDS
    expected = feed.get("expected_quotes_per_min", 0) or 1
    rate_ok = feed.get("quotes_per_min", 0) >= MIN_QUOTE_RATE_FRACTION * expected
    if stale and gaps:
        status = "down"
    elif stale or gaps or not rate_ok:
        status = "degraded"
    else:
        status = "ok"
    return {
        "name": feed.get("name", "unknown"),
        "status": status,
        "stale": stale,
        "gaps": gaps,
        "rate_ok": rate_ok,
    }


if __name__ == "__main__":
    demo = {
        "name": "equity-quotes",
        "last_update_age_s": 2,
        "received_seqs": [101, 102, 104, 105],
        "quotes_per_min": 950,
        "expected_quotes_per_min": 1000,
    }
    print(check_feed(demo))
