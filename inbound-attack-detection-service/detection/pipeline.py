"""Synthetic data generation + end-to-end pipeline.

Generates seeded synthetic messages (legitimate, phishing, BEC, and
legitimate bulk mail), scores them, stores results in SQLite, and
writes a JSON evaluation report. All data is invented locally; no real
email content is used anywhere.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from .classifier import AttackScorer
from .evaluation import evaluate, evaluate_by_segment, threshold_sweep
from .triage import triage_message

TRUSTED_DOMAIN = "acmecorp.com"

# --- Synthetic message templates -------------------------------------------

LEGIT_SENDERS = [
    ("alice.johnson@acmecorp.com", "Alice Johnson"),
    ("bob.lee@acmecorp.com", "Bob Lee"),
    ("carol.wu@acme-partners.com", "Carol Wu"),
    ("dave.m@acmecorp.com", "Dave Miller"),
]
LEGIT_SUBJECTS = [
    "Q3 roadmap review — notes attached",
    "Team lunch next Thursday",
    "Updated onboarding checklist",
    "Re: vendor contract renewal",
    "Slides for tomorrow's all-hands",
]
LEGIT_BODIES = [
    "Hi team, sharing the notes from today's review. Let me know if anything is missing.",
    "Quick reminder that the team lunch is next Thursday at noon. Please RSVP.",
    "Attached is the updated checklist. Ping me with any questions.",
]

PHISHING_SENDERS = [
    ("support@acmec0rp.com", "IT Support"),
    ("billing@acme-secure-login.xyz", "Billing Team"),
    ("security@invoice-pay.top", "Security Alert"),
    ("sarah chen@acmecorp-support.xyz", "Sarah Chen"),
]
PHISHING_SUBJECTS = [
    "URGENT: Verify your account immediately",
    "Your password expires today — action required",
    "Payment overdue — click here to resolve",
    "Invoice attached — wire transfer needed ASAP",
]
PHISHING_BODIES = [
    "Your account will be suspended. Verify your account immediately at https://acme-secure-login.xyz/verify.",
    "Click here to reset your password: http://192.168.4.20/reset. Action required now.",
    "Please process the attached invoice. Wire transfer needed ASAP — gift card payment also accepted.",
]

BEC_SENDERS = [
    ("sarah chen@acmecorp-payments.com", "Sarah Chen"),
    ("michael ortiz@acme-corp-finance.net", "Michael Ortiz"),
    ("priya nair@acmec0rp.com", "Priya Nair"),
]
BEC_SUBJECTS = [
    "Confidential — urgent wire transfer",
    "Quick favor — gift cards needed",
    "Re: payment — please process today",
]
BEC_BODIES = [
    "Hi, I'm in meetings all day. Please send a wire transfer for $48,000 to the vendor below. Confidential, do not share.",
    "Can you pick up gift cards for the client event? Urgent, I need this immediately.",
    "Please process this invoice today. The details are in the attached document.",
]

BULK_SENDERS = [
    ("news@techweekly.example", "Tech Weekly"),
    ("deals@shopdaily.example", "Shop Daily"),
    ("updates@conference.example", "Conference Updates"),
]
BULK_SUBJECTS = [
    "This week's top stories in tech",
    "50% off — this weekend only",
    "Your conference schedule is ready",
]
BULK_BODIES = [
    "Here is this week's newsletter. Read the top stories and unsubscribe anytime.",
    "Big sale this weekend! Shop now at https://shopdaily.example/sale.",
]


def _make_message(rng: random.Random, kind: str, i: int) -> dict:
    """Build one synthetic message of a given kind."""
    if kind == "phishing":
        sender, name = rng.choice(PHISHING_SENDERS)
        msg = {
            "id": f"phish-{i}",
            "sender": sender,
            "display_name": name,
            "reply_to": rng.choice(["support@acmec0rp.com", "help@invoice-pay.top"]),
            "subject": rng.choice(PHISHING_SUBJECTS),
            "body": rng.choice(PHISHING_BODIES),
            "attachments": rng.choice([[], [], ["invoice.pdf"], ["payment-details.zip"]]),
            "spf_pass": rng.choice([False, False, True]),
            "dkim_pass": rng.choice([False, False, True]),
            "dmarc_pass": False,
            "known_sender": False,
            "label": 1,
            "segment": "phishing",
        }
    elif kind == "bec":
        sender, name = rng.choice(BEC_SENDERS)
        msg = {
            "id": f"bec-{i}",
            "sender": sender,
            "display_name": name,
            "reply_to": sender,
            "subject": rng.choice(BEC_SUBJECTS),
            "body": rng.choice(BEC_BODIES),
            "attachments": rng.choice([[], ["invoice.docx"], ["wire-instructions.pdf"]]),
            "spf_pass": rng.choice([False, True]),
            "dkim_pass": rng.choice([False, True]),
            "dmarc_pass": rng.choice([False, True]),
            "known_sender": False,
            "label": 1,
            "segment": "bec",
        }
    elif kind == "bulk":
        sender, name = rng.choice(BULK_SENDERS)
        msg = {
            "id": f"bulk-{i}",
            "sender": sender,
            "display_name": name,
            "reply_to": sender,
            "subject": rng.choice(BULK_SUBJECTS),
            "body": rng.choice(BULK_BODIES),
            "attachments": [],
            "spf_pass": True,
            "dkim_pass": True,
            "dmarc_pass": True,
            "known_sender": False,
            "label": 0,
            "segment": "bulk",
        }
    else:  # legitimate
        sender, name = rng.choice(LEGIT_SENDERS)
        msg = {
            "id": f"legit-{i}",
            "sender": sender,
            "display_name": name,
            "reply_to": sender,
            "subject": rng.choice(LEGIT_SUBJECTS),
            "body": rng.choice(LEGIT_BODIES),
            "attachments": rng.choice([[], [], ["notes.pdf"]]),
            "spf_pass": True,
            "dkim_pass": True,
            "dmarc_pass": True,
            "known_sender": True,
            "label": 0,
            "segment": "legitimate",
        }
    msg["urls"] = None  # extracted from body by feature extraction
    return msg


def generate_dataset(seed: int = 42, counts: dict | None = None) -> list[dict]:
    """Seeded synthetic dataset. Default: 60 legit, 40 phishing, 25 BEC, 25 bulk."""
    counts = counts or {"legitimate": 60, "phishing": 40, "bec": 25, "bulk": 25}
    rng = random.Random(seed)
    messages: list[dict] = []
    for kind, n in counts.items():
        messages.extend(_make_message(rng, kind, i) for i in range(n))
    rng.shuffle(messages)
    return messages


def run_pipeline(
    seed: int = 42,
    db_path: str | Path = "detection_results.db",
    report_path: str | Path = "detection_report.json",
) -> dict:
    """Ingest → normalize → score → store → report. Returns the report dict."""
    messages = generate_dataset(seed=seed)
    scorer = AttackScorer()
    # Split: first 100 messages calibrate the threshold, rest are held out.
    train, heldout = messages[:100], messages[100:]
    train_info = scorer.train(train, [m["label"] for m in train])

    scored = []
    for msg in messages:
        result = scorer.score_message(msg)
        verdict = triage_message(msg, result) if result["label"] == "attack" else None
        scored.append({
            "id": msg["id"],
            "segment": msg["segment"],
            "label": msg["label"],
            "sender": msg["sender"],
            "subject": msg["subject"],
            "score": result["score"],
            "predicted": 1 if result["label"] == "attack" else 0,
            "top_signals": result["top_signals"],
            "triage": verdict,
        })

    # Persist to SQLite.
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS scored_messages")
        conn.execute(
            """CREATE TABLE scored_messages (
                id TEXT PRIMARY KEY, segment TEXT, label INTEGER,
                sender TEXT, subject TEXT, score REAL, predicted INTEGER,
                verdict TEXT
            )"""
        )
        conn.executemany(
            "INSERT INTO scored_messages VALUES (?,?,?,?,?,?,?,?)",
            [
                (s["id"], s["segment"], s["label"], s["sender"], s["subject"],
                 s["score"], s["predicted"],
                 s["triage"]["verdict"] if s["triage"] else None)
                for s in scored
            ],
        )
        conn.commit()
    finally:
        conn.close()

    labels = [s["label"] for s in scored]
    scores = [s["score"] for s in scored]
    segments = [s["segment"] for s in scored]
    report = {
        "dataset": {"n_messages": len(messages), "seed": seed,
                    "counts": {k: sum(1 for m in messages if m["segment"] == k)
                               for k in ("legitimate", "phishing", "bec", "bulk")}},
        "threshold_calibration": train_info,
        "threshold": scorer.threshold,
        "overall": evaluate(labels, scores, scorer.threshold),
        "by_segment": evaluate_by_segment(labels, scores, segments, scorer.threshold),
        "threshold_sweep": threshold_sweep(labels, scores),
        "triage_counts": {
            v: sum(1 for s in scored if s["triage"] and s["triage"]["verdict"] == v)
            for v in ("quarantine", "escalate", "allow")
        },
        "messages": scored,
    }
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def format_report(report: dict) -> str:
    """Human-readable summary of a pipeline report."""
    o = report["overall"]
    lines = [
        "Inbound Attack Detection — report",
        f"Messages scored: {o['n']} ({report['dataset']['counts']})",
        f"Threshold (F1-calibrated on train split): {report['threshold']}",
        f"Precision: {o['precision']:.3f}   Recall: {o['recall']:.3f}   "
        f"F1: {o['f1']:.3f}   ROC-AUC: {o['roc_auc']:.3f}",
        f"Confusion matrix: TP={o['confusion_matrix']['tp']} "
        f"FP={o['confusion_matrix']['fp']} TN={o['confusion_matrix']['tn']} "
        f"FN={o['confusion_matrix']['fn']}",
        "Per-segment F1:",
    ]
    for seg, ev in report["by_segment"].items():
        lines.append(
            f"  {seg:12s} precision={ev['precision']:.3f} recall={ev['recall']:.3f} "
            f"F1={ev['f1']:.3f} (n={ev['n']})"
        )
    lines.append(f"Triage verdicts on flagged messages: {report['triage_counts']}")
    return "\n".join(lines)
