import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.sources import (CsvSource, JsonLinesSource, PagedApiSource,
                                          read_raw_zone, write_raw_zone)


def test_csv_source_tags_provenance():
    rows = CsvSource("policy_extract", "2.1").read("policy_id,premium_annual\nPOL-1,100\n")
    assert len(rows) == 1
    assert rows[0].source == "policy_extract"
    assert rows[0].schema_version == "2.1"
    assert rows[0].data["policy_id"] == "POL-1"


def test_jsonl_source_skips_blank_lines():
    rows = JsonLinesSource("feed").read('{"a": 1}\n\n{"a": 2}\n')
    assert [r.data["a"] for r in rows] == [1, 2]


def test_paged_api_retries_once_then_succeeds():
    pages = [[{"id": 1}], [{"id": 2}]]
    rows = PagedApiSource("api", pages, fail_page_once=0).read()
    assert [r.data["id"] for r in rows] == [1, 2]


def test_raw_zone_roundtrip(tmp_path):
    rows = CsvSource("src", "1.0").read("policy_id\nP1\nP2\n")
    written = write_raw_zone(rows, str(tmp_path), date(2026, 11, 20))
    assert len(written) == 1
    assert "date=2026-11-20" in written[0]
    back = read_raw_zone(str(tmp_path), "src", date(2026, 11, 20))
    assert [r.data["policy_id"] for r in back] == ["P1", "P2"]
    assert back[0].source == "src"
