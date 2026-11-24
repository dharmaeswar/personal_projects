"""Evidence-grounded draft evaluation: the Solstice-style layer.

An agent that drafts content from approved evidence must be checked the
way a medical-legal-regulatory reviewer would check it: every claim in
the draft has to trace to an approved source *and* to the version of that
source that was current when the draft was generated. A claim that cites
a superseded version, a source the drafter may not see, or words no
approved source supports is a failure, even if the draft reads well.

This module adds three pieces to the harness:

- ``EvidenceStore`` — versioned approved content, with per-source access
  roles and keyword search. Retrieval returns the source id and version
  with every result, and refuses sources the caller's role may not see.
- ``DraftEvaluator`` — checks each draft claim against the store: the
  cited source must exist, the cited version must be current, the claim
  text must be supported by the cited source, and the caller's role must
  be allowed to read it. One verdict per claim plus a groundedness rate.
- ``ReviewFeedback`` — reviewer corrections captured per claim. Applying
  feedback boosts the corrected source in later retrieval, so the next
  draft starts from what reviewers already approved — the review-to-draft
  loop, scoped per brand.

All data is synthetic and lives in memory. No model API is called: the
draft claims are fixed inputs, so every evaluation is reproducible.
"""

from __future__ import annotations

import re


def _keywords(text):
    """Lowercase word tokens, minus a small stop-word list."""
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "are",
            "was", "were", "for", "with", "on", "by", "at", "as", "it",
            "this", "that", "from", "be", "has", "have", "not", "no"}
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in stop}


class EvidenceStore:
    """Versioned approved content with role-based access control.

    Each source has an id, a brand, a list of versions (each a dict with
    ``version`` and ``text``), and the roles allowed to read it. Versions
    are append-only: adding a new version never rewrites an old one, so a
    draft generated against v1 stays traceable after v2 is published.
    """

    def __init__(self, sources):
        self.sources = {}
        for src in sources:
            self.sources[src["source_id"]] = {
                "source_id": src["source_id"],
                "brand": src["brand"],
                "allowed_roles": set(src.get("allowed_roles", ())),
                "versions": list(src["versions"]),
            }
        # Reviewer feedback boosts: source_id -> number of approved uses.
        self.feedback_boost = {}

    def current_version(self, source_id):
        src = self.sources.get(source_id)
        if src is None:
            return None
        return src["versions"][-1]["version"]

    def get(self, source_id, version=None, role=None):
        """Return (version, text) for a source, or None if not found.

        ``version=None`` returns the current version. ``role`` is checked
        against the source's allowed roles; a denied role gets None.
        """
        src = self.sources.get(source_id)
        if src is None:
            return None
        if role is not None and role not in src["allowed_roles"]:
            return None
        if version is None:
            latest = src["versions"][-1]
            return latest["version"], latest["text"]
        for v in src["versions"]:
            if v["version"] == version:
                return v["version"], v["text"]
        return None

    def search(self, query, role, brand=None, limit=5):
        """Retrieve approved sources matching ``query`` for ``role``.

        Results are ranked by reviewer-feedback boost first, then keyword
        overlap. Each result carries the source id and the current version,
        so a draft built from it can cite exactly what it used.
        """
        terms = _keywords(query)
        scored = []
        for src in self.sources.values():
            if role not in src["allowed_roles"]:
                continue
            if brand is not None and src["brand"] != brand:
                continue
            text = src["versions"][-1]["text"]
            overlap = len(terms & _keywords(text))
            if overlap == 0:
                continue
            boost = self.feedback_boost.get(src["source_id"], 0)
            scored.append((boost, overlap, src["source_id"]))
        scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
        results = []
        for _, _, source_id in scored[:limit]:
            version, text = self.get(source_id, role=role)
            results.append({"source_id": source_id, "version": version,
                            "text": text,
                            "brand": self.sources[source_id]["brand"]})
        return results

    def record_feedback(self, source_id, approved=True):
        """Log one reviewer decision for a source (approved use only)."""
        if approved and source_id in self.sources:
            self.feedback_boost[source_id] = \
                self.feedback_boost.get(source_id, 0) + 1


class DraftClaim:
    """One claim in a draft, with the source + version it cites."""

    def __init__(self, claim_id, text, cited_source, cited_version):
        self.claim_id = claim_id
        self.text = text
        self.cited_source = cited_source
        self.cited_version = cited_version


class ClaimVerdict:
    """The evaluation outcome for one claim."""

    def __init__(self, claim, verdict, detail):
        self.claim = claim
        self.verdict = verdict  # supported | unsupported | stale-version |
        #                         unknown-source | access-denied
        self.detail = detail

    def to_dict(self):
        return {"claim_id": self.claim.claim_id,
                "text": self.claim.text,
                "cited_source": self.claim.cited_source,
                "cited_version": self.claim.cited_version,
                "verdict": self.verdict, "detail": self.detail}


class DraftEvaluator:
    """Check every claim in a draft against the evidence store."""

    def __init__(self, store, role):
        self.store = store
        self.role = role

    def evaluate(self, claims):
        verdicts = []
        for claim in claims:
            verdicts.append(self._check(claim))
        supported = sum(1 for v in verdicts if v.verdict == "supported")
        return {"verdicts": verdicts,
                "total": len(verdicts), "supported": supported,
                "groundedness": round(supported / len(verdicts), 4)
                if verdicts else 1.0}

    def _check(self, claim):
        src = self.store.sources.get(claim.cited_source)
        if src is None:
            return ClaimVerdict(claim, "unknown-source",
                                f"source {claim.cited_source} is not in "
                                "the approved evidence store")
        if self.role not in src["allowed_roles"]:
            return ClaimVerdict(claim, "access-denied",
                                f"role {self.role} may not read "
                                f"{claim.cited_source}")
        current = self.store.current_version(claim.cited_source)
        if claim.cited_version != current:
            return ClaimVerdict(claim, "stale-version",
                                f"cited v{claim.cited_version} but "
                                f"v{current} is current")
        _, text = self.store.get(claim.cited_source,
                                 version=claim.cited_version,
                                 role=self.role)
        claim_terms = _keywords(claim.text)
        source_terms = _keywords(text)
        missing = sorted(claim_terms - source_terms)
        if missing:
            return ClaimVerdict(claim, "unsupported",
                                "claim words not in the cited source: "
                                + ", ".join(missing))
        return ClaimVerdict(claim, "supported",
                            f"every claim word appears in "
                            f"{claim.cited_source} v{current}")


class ReviewFeedback:
    """One reviewer correction, applied so the next draft improves.

    A correction names the claim, the replacement wording, and the reason.
    Applying it records an approval boost for the source the corrected
    claim now rests on, so retrieval ranks reviewer-approved sources
    first for that brand in future drafts.
    """

    def __init__(self, claim_id, corrected_text, reason, source_id, brand):
        self.claim_id = claim_id
        self.corrected_text = corrected_text
        self.reason = reason
        self.source_id = source_id
        self.brand = brand

    def apply(self, store):
        store.record_feedback(self.source_id, approved=True)
        return {"claim_id": self.claim_id, "source_id": self.source_id,
                "brand": self.brand, "reason": self.reason,
                "boost": store.feedback_boost.get(self.source_id, 0)}


# ---------------------------------------------------------------------------
# Synthetic approved evidence. Invented brands and wording for the harness.
# ---------------------------------------------------------------------------

EVIDENCE_SOURCES = [
    {"source_id": "SRC-PI-101", "brand": "BrandA",
     "allowed_roles": ("drafter", "reviewer", "medical"),
     "versions": [
         {"version": 1,
          "text": "BrandA tablets are taken once daily with food. "
                  "Common side effects include headache and nausea."},
         {"version": 2,
          "text": "BrandA tablets are taken once daily with food. "
                  "Common side effects include headache, nausea and "
                  "dizziness. Do not use with strong CYP3A inhibitors."}]},
    {"source_id": "SRC-STUDY-202", "brand": "BrandA",
     "allowed_roles": ("drafter", "reviewer", "medical"),
     "versions": [
         {"version": 1,
          "text": "In the 12 week trial, 68 percent of patients reached "
                  "the primary endpoint, compared with 41 percent on "
                  "placebo. Discontinuation for adverse events was 4 "
                  "percent."}]},
    {"source_id": "SRC-PI-303", "brand": "BrandB",
     "allowed_roles": ("reviewer", "medical"),
     "versions": [
         {"version": 1,
          "text": "BrandB infusion is given every 4 weeks in clinic. "
                  "Monitor liver function before each dose."}]},
]

# Draft scenarios: each is a list of claims against the evidence above.
DRAFT_SCENARIOS = {
    "draft-clean": [
        DraftClaim("C1", "BrandA tablets are taken once daily with food",
                   "SRC-PI-101", 2),
        DraftClaim("C2", "68 percent of patients reached the primary endpoint",
                   "SRC-STUDY-202", 1),
    ],
    "draft-stale": [
        DraftClaim("C1", "BrandA tablets are taken once daily with food",
                   "SRC-PI-101", 1),
    ],
    "draft-unsupported": [
        DraftClaim("C1", "BrandA tablets cure migraines permanently",
                   "SRC-PI-101", 2),
    ],
    "draft-unknown-source": [
        DraftClaim("C1", "BrandA tablets are taken once daily with food",
                   "SRC-PI-999", 1),
    ],
}


def build_store():
    """A fresh evidence store from the synthetic sources."""
    return EvidenceStore(EVIDENCE_SOURCES)
