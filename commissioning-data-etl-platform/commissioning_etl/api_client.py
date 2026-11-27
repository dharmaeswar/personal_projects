"""Paginated API clients for commissioning systems and tickets.

The clients read local JSON fixture files and model the behaviour of the
real paginated REST APIs they stand in for: page-by-page reads, transient
failures that a retry should survive, and re-delivered records.
"""

import json
import os
import time


class ApiError(Exception):
    """A non-transient API failure."""


class TransientApiError(Exception):
    """A transient failure (timeout / 429 / 5xx) worth retrying."""


class PagedApiClient:
    """One paginated resource: ``list_page(page)`` + ``fetch_all()``."""

    def __init__(self, data_file, page_size=5, fail_first_page_once=False):
        self.data_file = data_file
        self.page_size = page_size
        self.fail_first_page_once = fail_first_page_once
        self._failed_once = False
        with open(data_file, encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, list):
            raise ApiError(f"{data_file}: expected a JSON list at the top level")
        self._records = payload

    def list_page(self, page):
        """Return one page: {'items': [...], 'page': n, 'total_pages': m}."""
        if page < 1:
            raise ApiError(f"page must be >= 1, got {page}")
        if self.fail_first_page_once and not self._failed_once and page == 1:
            self._failed_once = True
            raise TransientApiError("simulated transient failure on page 1")
        total = len(self._records)
        total_pages = max(1, -(-total // self.page_size))
        if page > total_pages:
            return {"items": [], "page": page, "total_pages": total_pages}
        start = (page - 1) * self.page_size
        return {
            "items": self._records[start:start + self.page_size],
            "page": page,
            "total_pages": total_pages,
        }

    def fetch_all(self, max_retries=3, backoff_seconds=0.01):
        """Walk every page, retrying transient failures with backoff."""
        items = []
        page = 1
        while True:
            attempt = 0
            while True:
                try:
                    result = self.list_page(page)
                    break
                except TransientApiError:
                    attempt += 1
                    if attempt > max_retries:
                        raise
                    time.sleep(backoff_seconds * attempt)
            items.extend(result["items"])
            if page >= result["total_pages"]:
                return items
            page += 1


def make_clients(data_dir, fail_first_page_once=False):
    """Build the commissioning-systems and ticketing clients."""
    return {
        "systems": PagedApiClient(
            os.path.join(data_dir, "commissioning_systems.json"),
            fail_first_page_once=fail_first_page_once,
        ),
        "tickets": PagedApiClient(
            os.path.join(data_dir, "tickets.json"),
            fail_first_page_once=fail_first_page_once,
        ),
    }
