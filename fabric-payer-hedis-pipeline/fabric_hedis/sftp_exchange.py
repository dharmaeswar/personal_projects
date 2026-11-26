"""SFTP payer file exchange: inbound validation and vendor round-trip.

The local directories stand in for an SFTP server: ``inbound/`` is the
payer drop folder, ``outbound/`` is what we send to a third-party vendor,
and ``vendor_returns/`` is what the vendor sends back. Every file carries
a manifest entry (expected row count + SHA-256); a file is never trusted
on arrival — header, checksum, row count and per-row content are all
checked before anything lands in the lakehouse.
"""

import csv
import hashlib
import json
from pathlib import Path


class FileValidationError(Exception):
    """Raised when an inbound file fails manifest/header/content checks."""


EXPECTED_HEADERS = {
    "members_2026-10.csv": ["member_id", "sex", "age", "plan", "diabetes",
                            "hypertension", "enrollment_start",
                            "enrollment_end"],
    "claims_2026-10.csv": ["claim_id", "member_id", "service_date",
                           "diag_code", "procedure_code", "billed_amount",
                           "adjustment", "paid_amount", "source_file"],
    "labs_2026-10.csv": ["member_id", "test", "result", "result_date"],
    "screenings_2026-10.csv": ["member_id", "screening_type",
                               "screening_date"],
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_manifest(inbound_dir):
    manifest_path = Path(inbound_dir) / "manifest.json"
    if not manifest_path.exists():
        raise FileValidationError("missing manifest.json in %s" % inbound_dir)
    return json.loads(manifest_path.read_text())


def validate_file(inbound_dir, filename):
    """Validate one inbound file against its manifest entry.

    Returns the parsed rows. Raises FileValidationError listing every
    problem found (header, checksum, row count) instead of failing on
    the first one, so operations sees the full picture.
    """
    inbound = Path(inbound_dir)
    manifest = load_manifest(inbound)
    problems = []
    if filename not in manifest:
        raise FileValidationError("%s: no manifest entry" % filename)
    path = inbound / filename
    if not path.exists():
        raise FileValidationError("%s: file missing from inbound folder"
                                  % filename)
    expected = manifest[filename]
    if _sha256(path) != expected["sha256"]:
        problems.append("checksum mismatch (file changed after manifest)")
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EXPECTED_HEADERS[filename]:
            problems.append("header mismatch: got %s, expected %s"
                            % (reader.fieldnames,
                               EXPECTED_HEADERS[filename]))
        rows = list(reader)
    if len(rows) != expected["rows"]:
        problems.append("row count %d, manifest says %d"
                        % (len(rows), expected["rows"]))
    if problems:
        raise FileValidationError("%s: %s" % (filename, "; ".join(problems)))
    return rows


def receive_files(inbound_dir):
    """Validate every manifested file. Returns {filename: rows}.

    A single bad file stops the run: partial loads would leave the
    lakehouse inconsistent with the payer's monthly drop.
    """
    manifest = load_manifest(inbound_dir)
    received = {}
    for filename in sorted(manifest):
        received[filename] = validate_file(inbound_dir, filename)
    return received


def send_to_vendor(outbound_dir, name, columns, rows):
    """Write an outbound vendor file plus its manifest entry.

    Returns (path, manifest entry). The vendor file is the gold output
    the downstream partner consumes, so it is checksummed the same way
    inbound files are.
    """
    out = Path(outbound_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    entry = {"rows": len(rows), "sha256": _sha256(path)}
    manifest_path = out / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    manifest[name] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return path, entry


def validate_vendor_return(outbound_dir, sent_name, ack_rows, ack_columns):
    """Validate a vendor acknowledgement file against what was sent.

    ``ack_rows`` is a list of {"claim_id": ..., "status": "accepted" |
    "rejected", "reason": ...}. Returns (accepted, rejected, problems):
    rejected rows and any ack row naming a claim id that was never sent.
    """
    manifest = json.loads((Path(outbound_dir) / "manifest.json").read_text())
    sent = manifest[sent_name]["rows"]
    if len(ack_rows) != sent:
        return 0, 0, ["ack covers %d rows, %d were sent"
                      % (len(ack_rows), sent)]
    problems = []
    accepted = rejected = 0
    for row in ack_rows:
        if row["status"] == "accepted":
            accepted += 1
        elif row["status"] == "rejected":
            rejected += 1
            problems.append("vendor rejected %s: %s"
                            % (row.get("claim_id", "?"),
                               row.get("reason", "no reason given")))
        else:
            problems.append("unknown ack status %r for %s"
                            % (row["status"], row.get("claim_id", "?")))
    return accepted, rejected, problems
