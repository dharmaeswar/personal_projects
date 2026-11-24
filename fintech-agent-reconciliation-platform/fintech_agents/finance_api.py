"""REST API + OAuth client for Finance systems — the ERP / planning /
CRM integration shape the posting names.

A fake in-memory transport stands in for the real ERP: it pages
invoice lists, enforces a rate limit (HTTP 429 with Retry-After),
expires OAuth tokens, and honours idempotency keys so a retried
journal-entry POST never books twice. The client handles all of
that: token fetch and refresh, cursor pagination, 429 backoff, and
idempotency-key reuse on retries. Nothing here calls a real API.
"""

from __future__ import annotations

import time


class RateLimited(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__(f"rate limited, retry after "
                         f"{retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


class Unauthorized(Exception):
    """The access token expired or was never issued."""


class FakeErpTransport:
    """In-memory ERP: paginated invoices, a rate limit, expiring
    tokens, and idempotent journal entries."""

    def __init__(self, invoices: list[dict], *, page_size: int = 2,
                 rate_limit_calls: int = 4,
                 token_uses: int = 3) -> None:
        self.invoices = list(invoices)
        self.page_size = page_size
        self.rate_limit_calls = rate_limit_calls
        self.token_uses = token_uses
        self.calls = 0
        self._token = None
        self._token_remaining = 0
        self.journal: dict[str, dict] = {}
        self.posted_entries: list[dict] = []

    def fetch_token(self) -> str:
        self._token = f"tok-{self.calls}-{int(time.time())}"
        self._token_remaining = self.token_uses
        return self._token

    def _check_auth(self, token: str) -> None:
        if token != self._token or self._token_remaining <= 0:
            raise Unauthorized("access token expired or invalid")
        self._token_remaining -= 1

    def _check_rate(self) -> None:
        # A quota window: after rate_limit_calls calls the next call
        # is refused with 429, then the window refills so a retried
        # call succeeds — the shape of a real rate limit, not a lock.
        self.calls += 1
        if self.calls > self.rate_limit_calls:
            self.calls = 0
            raise RateLimited(retry_after_seconds=0.01)

    def list_invoices(self, token: str,
                      cursor: str | None = None) -> dict:
        self._check_auth(token)
        self._check_rate()
        start = int(cursor) if cursor else 0
        page = self.invoices[start:start + self.page_size]
        next_cursor = (str(start + self.page_size)
                       if start + self.page_size < len(self.invoices)
                       else None)
        return {"invoices": page, "next_cursor": next_cursor}

    def post_journal_entry(self, token: str, payload: dict,
                           idempotency_key: str) -> dict:
        self._check_auth(token)
        self._check_rate()
        if idempotency_key in self.journal:
            return {"status": "replayed",
                    "entry": self.journal[idempotency_key]}
        entry = {"entry_id": f"JE-{len(self.posted_entries) + 1:04d}",
                 **payload}
        self.journal[idempotency_key] = entry
        self.posted_entries.append(entry)
        return {"status": "created", "entry": entry}


class FinanceApiClient:
    """OAuth client-credentials client with pagination, 429 backoff
    and idempotent writes."""

    def __init__(self, transport: FakeErpTransport,
                 *, max_retries: int = 3) -> None:
        self.transport = transport
        self.max_retries = max_retries
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token is None:
            self._access_token = self.transport.fetch_token()
        return self._access_token

    def _call(self, fn, *args, **kwargs):
        """One transport call with token refresh on 401 and backoff
        on 429, up to max_retries of each kind."""
        auth_retries = 0
        rate_retries = 0
        while True:
            try:
                return fn(self._token(), *args, **kwargs)
            except Unauthorized:
                auth_retries += 1
                if auth_retries > self.max_retries:
                    raise
                self._access_token = self.transport.fetch_token()
            except RateLimited as exc:
                rate_retries += 1
                if rate_retries > self.max_retries:
                    raise
                time.sleep(exc.retry_after_seconds)

    def list_all_invoices(self) -> list[dict]:
        out: list[dict] = []
        cursor: str | None = None
        while True:
            page = self._call(self.transport.list_invoices,
                              cursor=cursor)
            out.extend(page["invoices"])
            cursor = page["next_cursor"]
            if cursor is None:
                return out

    def post_journal_entry(self, payload: dict,
                           idempotency_key: str) -> dict:
        return self._call(self.transport.post_journal_entry, payload,
                          idempotency_key)
