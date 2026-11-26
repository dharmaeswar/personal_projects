"""Tests for the SFTP payer file exchange (inbound validation, vendor)."""

import csv
import json

import pytest

from fabric_hedis import seed
from fabric_hedis.sftp_exchange import (FileValidationError, receive_files,
                                        send_to_vendor,
                                        validate_file,
                                        validate_vendor_return)


def test_seed_is_deterministic():
    assert seed.build_seed_data(42) == seed.build_seed_data(42)
    data = seed.build_seed_data(42)
    assert len(data["members"]) == 60
    assert len(data["claims"]) == 186  # 180 clean + 6 planted defects


def test_receive_files_ok(tmp_path):
    seed.write_inbound_files(tmp_path)
    received = receive_files(tmp_path)
    assert sorted(received) == ["claims_2026-10.csv", "labs_2026-10.csv",
                                "members_2026-10.csv",
                                "screenings_2026-10.csv"]
    assert len(received["claims_2026-10.csv"]) == 186
    assert len(received["members_2026-10.csv"]) == 60


def test_checksum_mismatch_is_caught(tmp_path):
    seed.write_inbound_files(tmp_path)
    path = tmp_path / "claims_2026-10.csv"
    with open(path, "a") as fh:
        fh.write("C99999,M0001,2026-10-01,E11.9,99213,10.00,0.00,10.00,x\n")
    with pytest.raises(FileValidationError) as exc:
        validate_file(tmp_path, "claims_2026-10.csv")
    assert "checksum mismatch" in str(exc.value)
    assert "row count" in str(exc.value)


def test_header_mismatch_is_caught(tmp_path):
    seed.write_inbound_files(tmp_path)
    path = tmp_path / "labs_2026-10.csv"
    rows = list(csv.reader(open(path)))
    rows[0] = ["member_id", "test", "value", "result_date"]
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    with pytest.raises(FileValidationError) as exc:
        validate_file(tmp_path, "labs_2026-10.csv")
    assert "header mismatch" in str(exc.value)


def test_missing_manifest(tmp_path):
    with pytest.raises(FileValidationError):
        receive_files(tmp_path)


def test_missing_file(tmp_path):
    manifest = seed.write_inbound_files(tmp_path)
    (tmp_path / "labs_2026-10.csv").unlink()
    with pytest.raises(FileValidationError) as exc:
        validate_file(tmp_path, "labs_2026-10.csv")
    assert "missing" in str(exc.value)


def test_vendor_round_trip(tmp_path):
    out = tmp_path / "outbound"
    rows = [{"measure": "BCS", "rate": "0.5"},
            {"measure": "COL", "rate": "0.7"}]
    send_to_vendor(out, "hedis.csv", ["measure", "rate"], rows)
    ack = [{"claim_id": "BCS", "status": "accepted", "reason": ""},
           {"claim_id": "COL", "status": "accepted", "reason": ""}]
    accepted, rejected, problems = validate_vendor_return(
        out, "hedis.csv", ack, [])
    assert (accepted, rejected, problems) == (2, 0, [])


def test_vendor_rejection_is_reported(tmp_path):
    out = tmp_path / "outbound"
    rows = [{"measure": "BCS", "rate": "0.5"}]
    send_to_vendor(out, "hedis.csv", ["measure", "rate"], rows)
    ack = [{"claim_id": "BCS", "status": "rejected",
            "reason": "rate out of range"}]
    accepted, rejected, problems = validate_vendor_return(
        out, "hedis.csv", ack, [])
    assert accepted == 0 and rejected == 1
    assert "vendor rejected BCS" in problems[0]


def test_vendor_ack_row_count_mismatch(tmp_path):
    out = tmp_path / "outbound"
    send_to_vendor(out, "hedis.csv", ["measure"],
                   [{"measure": "BCS"}, {"measure": "COL"}])
    _, _, problems = validate_vendor_return(
        out, "hedis.csv",
        [{"claim_id": "BCS", "status": "accepted", "reason": ""}], [])
    assert "ack covers 1 rows, 2 were sent" in problems[0]
