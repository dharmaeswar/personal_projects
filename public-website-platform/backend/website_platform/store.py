"""In-memory store for the public website platform.

Kept deliberately small and dependency-free: the demo service runs from
this store, and the repository interface is the seam where a real database
(PostgreSQL) would plug in without touching the handlers.
"""

import threading


class Store:
    """Thread-safe in-memory store for pages, forms, events, consent."""

    def __init__(self):
        self.lock = threading.Lock()
        self.pages = {
            "home": {
                "slug": "home",
                "title": "Ship what's next",
                "blocks": [
                    {"type": "hero", "heading": "Ship what's next",
                     "body": "Build and deploy web applications with speed."},
                    {"type": "text", "heading": "Why this platform",
                     "body": "One codebase serves marketing pages, docs, and forms."},
                ],
            },
            "pricing": {
                "slug": "pricing",
                "title": "Pricing",
                "blocks": [
                    {"type": "hero", "heading": "Simple pricing",
                     "body": "Start free, scale when you need to."},
                ],
            },
        }
        # form_id -> {fields: [required field names], submissions: [...]}
        self.forms = {
            "contact": {"fields": ["name", "email", "message"], "submissions": []},
            "newsletter": {"fields": ["email"], "submissions": []},
        }
        self.events = []          # analytics events, consent-gated at intake
        self.consent = {}         # visitor_id -> {"analytics": bool, "marketing": bool}
        self.request_counts = {}  # (method, path, status) -> count

    def record_request(self, method, path, status):
        key = (method, path, status)
        with self.lock:
            self.request_counts[key] = self.request_counts.get(key, 0) + 1

    def get_page(self, slug):
        with self.lock:
            page = self.pages.get(slug)
            return dict(page) if page else None

    def list_pages(self):
        with self.lock:
            return [{"slug": p["slug"], "title": p["title"]}
                    for p in self.pages.values()]

    def submit_form(self, form_id, payload, idempotency_key):
        """Validate and store a form submission.

        Returns (status, body). Replaying an idempotency key returns the
        original submission with 200 instead of storing a duplicate.
        """
        with self.lock:
            form = self.forms.get(form_id)
            if form is None:
                return 404, {"error": "unknown form"}
            for sub in form["submissions"]:
                if sub["idempotency_key"] == idempotency_key:
                    return 200, {"id": sub["id"], "duplicate": True}
            missing = [f for f in form["fields"] if not payload.get(f)]
            if missing:
                return 400, {"error": "missing required fields",
                             "fields": missing}
            email = payload.get("email", "")
            if "@" not in email or "." not in email.split("@")[-1]:
                return 400, {"error": "invalid email", "fields": ["email"]}
            sub_id = "sub-%04d" % (len(form["submissions"]) + 1)
            form["submissions"].append({
                "id": sub_id, "idempotency_key": idempotency_key,
                "fields": {f: payload.get(f) for f in form["fields"]},
            })
            return 201, {"id": sub_id, "duplicate": False}

    def track_events(self, visitor_id, events):
        """Store a batch of analytics events. Consent is checked by the handler."""
        with self.lock:
            stored = []
            for event in events:
                record = {"visitor_id": visitor_id,
                          "name": event.get("name"),
                          "properties": event.get("properties") or {}}
                self.events.append(record)
                stored.append(record)
            return stored

    def get_consent(self, visitor_id):
        with self.lock:
            return dict(self.consent.get(
                visitor_id, {"analytics": False, "marketing": False}))

    def set_consent(self, visitor_id, consent):
        with self.lock:
            record = {"analytics": bool(consent.get("analytics", False)),
                      "marketing": bool(consent.get("marketing", False))}
            self.consent[visitor_id] = record
            return dict(record)
