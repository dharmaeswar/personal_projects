from fintech_agents.finance_api import (
    FakeErpTransport, FinanceApiClient, Unauthorized)


def _invoices(n=5):
    return [{"invoice_id": f"INV-{i}", "amount_minor": 100_000 * i}
            for i in range(1, n + 1)]


def test_pagination_collects_all_invoices():
    client = FinanceApiClient(FakeErpTransport(_invoices(), page_size=2))
    assert len(client.list_all_invoices()) == 5


def test_expired_token_is_refreshed_and_call_continues():
    # Token good for 1 call; 3 pages need 3 calls, so the client must
    # refresh twice mid-pagination.
    transport = FakeErpTransport(_invoices(), page_size=2, token_uses=1,
                                 rate_limit_calls=10)
    client = FinanceApiClient(transport)
    assert len(client.list_all_invoices()) == 5


def test_rate_limit_429_is_retried():
    # Quota of 1 call per window; 3 pages need 3 calls, so two 429s
    # must be absorbed by backoff retries.
    transport = FakeErpTransport(_invoices(), page_size=2,
                                 rate_limit_calls=1, token_uses=10)
    client = FinanceApiClient(transport)
    assert len(client.list_all_invoices()) == 5


def test_idempotent_post_never_books_twice():
    transport = FakeErpTransport(_invoices())
    client = FinanceApiClient(transport)
    payload = {"account": "accruals", "amount_minor": 5000}
    first = client.post_journal_entry(payload, "je-1")
    second = client.post_journal_entry(payload, "je-1")
    assert first["status"] == "created"
    assert second["status"] == "replayed"
    assert second["entry"]["entry_id"] == first["entry"]["entry_id"]
    assert len(transport.posted_entries) == 1


def test_different_idempotency_keys_book_separately():
    transport = FakeErpTransport(_invoices())
    client = FinanceApiClient(transport)
    client.post_journal_entry({"account": "a", "amount_minor": 1}, "k1")
    client.post_journal_entry({"account": "a", "amount_minor": 1}, "k2")
    assert len(transport.posted_entries) == 2


def test_stale_token_raises_without_client_refresh():
    transport = FakeErpTransport(_invoices())
    with __import__("pytest").raises(Unauthorized):
        transport.list_invoices("bogus-token")
