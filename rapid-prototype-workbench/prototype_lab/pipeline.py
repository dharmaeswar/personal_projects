"""Feedback pipeline: user feedback events -> trusted prototype metrics.

Raw feedback arrives as events (user id, prototype, rating 1-5, comment,
day). The pipeline ingests, validates, dedupes repeat submissions from
the same user on the same day, and aggregates per prototype: count,
average rating, share of promoters (rating 4-5), and per-day counts.
Invalid events are quarantined with a reason, never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeedbackEvent:
    user_id: str
    prototype_slug: str
    rating: int
    comment: str = ""
    day: str = ""  # YYYY-MM-DD


@dataclass
class Quarantined:
    event: dict
    reason: str


class FeedbackPipeline:
    """Ingest -> validate -> dedupe -> aggregate, in memory."""

    def __init__(self):
        self.events = []          # accepted FeedbackEvent objects
        self.quarantined = []     # Quarantined records with reasons
        self._seen_keys = set()   # (user_id, prototype_slug, day) dedupe keys

    def ingest(self, raw):
        """Accept one raw feedback dict. Returns 'accepted', 'duplicate' or 'quarantined'."""
        if not isinstance(raw, dict):
            self.quarantined.append(Quarantined(event={}, reason="event is not an object"))
            return "quarantined"
        user_id = raw.get("user_id")
        proto = raw.get("prototype_slug")
        rating = raw.get("rating")
        day = raw.get("day", "")
        comment = raw.get("comment", "")
        if not isinstance(user_id, str) or not user_id.strip():
            self.quarantined.append(Quarantined(event=dict(raw), reason="missing user_id"))
            return "quarantined"
        if not isinstance(proto, str) or not proto.strip():
            self.quarantined.append(Quarantined(event=dict(raw), reason="missing prototype_slug"))
            return "quarantined"
        if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
            self.quarantined.append(Quarantined(event=dict(raw), reason="rating must be an integer 1-5"))
            return "quarantined"
        if not isinstance(day, str) or len(day) != 10 or day[4] != "-" or day[7] != "-":
            self.quarantined.append(Quarantined(event=dict(raw), reason="day must be YYYY-MM-DD"))
            return "quarantined"
        if not isinstance(comment, str):
            self.quarantined.append(Quarantined(event=dict(raw), reason="comment must be text"))
            return "quarantined"
        key = (user_id.strip(), proto.strip(), day)
        if key in self._seen_keys:
            return "duplicate"
        self._seen_keys.add(key)
        self.events.append(FeedbackEvent(
            user_id=user_id.strip(), prototype_slug=proto.strip(),
            rating=rating, comment=comment.strip(), day=day))
        return "accepted"

    def ingest_many(self, raws):
        counts = {"accepted": 0, "duplicate": 0, "quarantined": 0}
        for raw in raws:
            counts[self.ingest(raw)] += 1
        return counts

    def metrics(self, prototype_slug):
        """Aggregate metrics for one prototype, or None when it has no feedback yet."""
        rows = [e for e in self.events if e.prototype_slug == prototype_slug]
        if not rows:
            return None
        ratings = [e.rating for e in rows]
        per_day = {}
        for e in rows:
            per_day[e.day] = per_day.get(e.day, 0) + 1
        return {
            "prototype_slug": prototype_slug,
            "count": len(rows),
            "avg_rating": round(sum(ratings) / len(ratings), 2),
            "promoter_share": round(sum(1 for r in ratings if r >= 4) / len(rows), 2),
            "detractor_share": round(sum(1 for r in ratings if r <= 2) / len(rows), 2),
            "per_day": dict(sorted(per_day.items())),
        }

    def comments(self, prototype_slug):
        return [e.comment for e in self.events
                if e.prototype_slug == prototype_slug and e.comment]
