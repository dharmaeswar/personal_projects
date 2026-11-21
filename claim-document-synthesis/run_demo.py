#!/usr/bin/env python3
"""CLI demo: ingest the seeded claim documents and print the outcome.

Usage: python run_demo.py [--count N]
"""
from __future__ import annotations

import argparse

from claim_synthesis.documents import generate_documents
from claim_synthesis.service import ClaimSynthesisService


def main() -> None:
    parser = argparse.ArgumentParser(description="Claim synthesis demo.")
    parser.add_argument("--count", type=int, default=24)
    args = parser.parse_args()
    service = ClaimSynthesisService()
    trusted = queued = 0
    for document in generate_documents(count=args.count):
        claim = service.ingest_claim(document)
        if claim["status"] == "trusted":
            trusted += 1
        else:
            queued += 1
    print(f"Ingested {service.store.count()} claims: "
          f"{trusted} trusted, {queued} queued for review.")
    for tenant in ("tenant_acme", "tenant_beacon"):
        pending = service.review_queue(tenant)
        print(f"Review queue ({tenant}): {len(pending)} pending")
        for item in pending:
            missing = [f for f, d in item["facts"].items() if d["value"] is None]
            print(f"  {item['claim_id']}: confidence {item['confidence']:.2f}, "
                  f"missing {missing or 'none'}")
    print(f"Audit log entries: {len(service.queue.audit_log)}")


if __name__ == "__main__":
    main()
