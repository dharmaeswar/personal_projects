"""Multi-source ETL ingest for the post-trade pipeline.

HRT's Python ETL work covers many input types, so the ingest stage
takes three: executions as CSV, market-data marks as CSV, and
free-text reference notes (one ``SYMBOL: note`` line each). Every row
is validated before it enters the pipeline; bad rows are quarantined
with a reason instead of being dropped silently or loaded dirty, and
duplicate execution ids are quarantined the same way. All inputs here
are seeded and synthetic.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from .models import ClearingRecord, Execution

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class QuarantinedRow:
    """One input row that failed validation, with the reason why."""

    source: str
    row_number: int
    raw: str
    reason: str


@dataclass
class IngestResult:
    """Outcome of ingesting one source: good records + quarantine."""

    records: list
    quarantined: list = field(default_factory=list)

    @property
    def loaded(self) -> int:
        return len(self.records)

    @property
    def rejected(self) -> int:
        return len(self.quarantined)


def _rows(text):
    reader = csv.DictReader(io.StringIO(text.strip()))
    for number, row in enumerate(reader, start=2):
        yield number, row


def parse_executions_csv(text):
    """Parse executions CSV into Execution records.

    Required columns: exec_id, symbol, side, quantity, price,
    trade_date, venue, account. Side must be BUY or SELL, quantity a
    positive integer, price a positive number, trade_date YYYY-MM-DD.
    A repeated exec_id is quarantined as a duplicate.
    """
    records, quarantined, seen = [], [], set()
    for number, row in _rows(text):
        raw = ",".join(str(v) for v in row.values())
        try:
            exec_id = (row.get("exec_id") or "").strip()
            symbol = (row.get("symbol") or "").strip()
            side = (row.get("side") or "").strip().upper()
            if not exec_id or not symbol:
                raise ValueError("missing exec_id or symbol")
            if exec_id in seen:
                raise ValueError(f"duplicate exec_id {exec_id}")
            if side not in ("BUY", "SELL"):
                raise ValueError(f"bad side {side!r}")
            quantity = int(row.get("quantity") or "")
            price = float(row.get("price") or "")
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            if price <= 0:
                raise ValueError("price must be positive")
            trade_date = (row.get("trade_date") or "").strip()
            if not _DATE_RE.match(trade_date):
                raise ValueError(f"bad trade_date {trade_date!r}")
            venue = (row.get("venue") or "").strip()
            account = (row.get("account") or "").strip()
            if not venue or not account:
                raise ValueError("missing venue or account")
        except (ValueError, TypeError) as exc:
            quarantined.append(QuarantinedRow("executions", number, raw, str(exc)))
            continue
        seen.add(exec_id)
        records.append(
            Execution(exec_id, symbol, side, quantity, price, trade_date, venue, account)
        )
    return IngestResult(records, quarantined)


def parse_marks_csv(text):
    """Parse mark prices CSV into a {symbol: price} dict.

    Required columns: symbol, price. Price must be a positive number.
    A repeated symbol keeps the first mark and quarantines the later
    row as a duplicate.
    """
    marks, quarantined, seen = {}, [], set()
    for number, row in _rows(text):
        raw = ",".join(str(v) for v in row.values())
        symbol = (row.get("symbol") or "").strip()
        try:
            if not symbol:
                raise ValueError("missing symbol")
            if symbol in seen:
                raise ValueError(f"duplicate mark for {symbol}")
            price = float(row.get("price") or "")
            if price <= 0:
                raise ValueError("price must be positive")
        except (ValueError, TypeError) as exc:
            quarantined.append(QuarantinedRow("marks", number, raw, str(exc)))
            continue
        seen.add(symbol)
        marks[symbol] = price
    return IngestResult(marks, quarantined)


def parse_clearing_csv(text):
    """Parse clearing records CSV into ClearingRecord records.

    Same validation shape as executions: side BUY/SELL, positive
    quantity and price, YYYY-MM-DD trade date, no duplicate ids.
    Fees default to 0.0 and must not be negative.
    """
    records, quarantined, seen = [], [], set()
    for number, row in _rows(text):
        raw = ",".join(str(v) for v in row.values())
        try:
            clearing_id = (row.get("clearing_id") or "").strip()
            symbol = (row.get("symbol") or "").strip()
            side = (row.get("side") or "").strip().upper()
            if not clearing_id or not symbol:
                raise ValueError("missing clearing_id or symbol")
            if clearing_id in seen:
                raise ValueError(f"duplicate clearing_id {clearing_id}")
            if side not in ("BUY", "SELL"):
                raise ValueError(f"bad side {side!r}")
            quantity = int(row.get("quantity") or "")
            price = float(row.get("price") or "")
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            if price <= 0:
                raise ValueError("price must be positive")
            trade_date = (row.get("trade_date") or "").strip()
            if not _DATE_RE.match(trade_date):
                raise ValueError(f"bad trade_date {trade_date!r}")
            account = (row.get("account") or "").strip()
            if not account:
                raise ValueError("missing account")
            fees = float(row.get("fees") or 0.0)
            if fees < 0:
                raise ValueError("fees must not be negative")
        except (ValueError, TypeError) as exc:
            quarantined.append(QuarantinedRow("clearing", number, raw, str(exc)))
            continue
        seen.add(clearing_id)
        records.append(
            ClearingRecord(clearing_id, symbol, side, quantity, price, trade_date, account, fees)
        )
    return IngestResult(records, quarantined)


def parse_text_notes(text):
    """Parse free-text reference notes, one ``SYMBOL: note`` per line.

    Blank lines are skipped. A line without ``:`` or without a symbol
    is quarantined as malformed; the note text itself is free-form.
    Returns an IngestResult of (symbol, note) tuples.
    """
    records, quarantined = [], []
    for number, line in enumerate(text.strip().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            quarantined.append(
                QuarantinedRow("notes", number, stripped, "malformed note line (no ':')")
            )
            continue
        symbol, note = stripped.split(":", 1)
        symbol, note = symbol.strip(), note.strip()
        if not symbol or not note:
            quarantined.append(
                QuarantinedRow("notes", number, stripped, "missing symbol or note text")
            )
            continue
        records.append((symbol, note))
    return IngestResult(records, quarantined)
