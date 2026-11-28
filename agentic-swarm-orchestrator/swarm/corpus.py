"""Seeded document corpus and questions with ground truth.

The swarm searches a large space of finance documents for the ones that
answer a question. Everything is generated from a fixed seed, so the corpus,
the questions, and the ground truth are identical on every run.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

TOPICS = [
    "invoice", "vendor", "refund", "payroll", "foreign-exchange",
    "tax", "travel", "procurement", "subscription", "reimbursement",
]

TOPIC_KEYWORDS = {
    "invoice": ["invoice", "billing", "payment due", "net 30", "po number"],
    "vendor": ["vendor", "supplier", "contract", "onboarding", "w9"],
    "refund": ["refund", "chargeback", "return", "credit memo", "dispute"],
    "payroll": ["payroll", "salary", "withholding", "pay period", "overtime"],
    "foreign-exchange": ["fx rate", "currency", "conversion", "spot rate", "hedge"],
    "tax": ["tax", "1099", "deduction", "withholding", "filing"],
    "travel": ["travel", "flight", "hotel", "per diem", "expense report"],
    "procurement": ["procurement", "purchase order", "requisition", "approval", "spend"],
    "subscription": ["subscription", "renewal", "license", "seat", "annual plan"],
    "reimbursement": ["reimbursement", "receipt", "mileage", "claim", "out of pocket"],
}

FILLER = [
    "quarterly review", "budget planning", "team offsite", "hiring plan",
    "office lease", "software audit", "security review", "all-hands",
    "vendor dinner", "conference", "training", "headcount", "roadmap",
    "retention", "onboarding", "compliance", "audit trail", "forecast",
]


@dataclass(frozen=True)
class Document:
    doc_id: str
    topic: str
    text: str


@dataclass(frozen=True)
class Question:
    question_id: str
    text: str
    topic: str
    keywords: tuple[str, ...]


@dataclass
class Corpus:
    documents: list[Document] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)

    def ground_truth(self, question: Question) -> set[str]:
        """Doc ids that actually answer the question: docs on its topic."""
        return {d.doc_id for d in self.documents if d.topic == question.topic}


def build_corpus(n_docs: int = 1200, seed: int = 20261118) -> Corpus:
    rng = random.Random(seed)
    documents: list[Document] = []
    for i in range(n_docs):
        topic = TOPICS[i % len(TOPICS)]
        keywords = rng.sample(TOPIC_KEYWORDS[topic], 3)
        filler = rng.sample(FILLER, 2)
        text = (
            f"Record {i + 1:04d} about {topic}: "
            + ", ".join(keywords)
            + ". Related: " + ", ".join(filler) + "."
        )
        documents.append(Document(doc_id=f"DOC-{i + 1:04d}", topic=topic, text=text))
    questions = [
        Question(
            question_id="Q1",
            text="Which records describe invoice billing and payment-due terms?",
            topic="invoice",
            keywords=("invoice", "billing", "payment due"),
        ),
        Question(
            question_id="Q2",
            text="Which records cover vendor onboarding and supplier contracts?",
            topic="vendor",
            keywords=("vendor", "supplier", "contract"),
        ),
        Question(
            question_id="Q3",
            text="Which records are about refunds, chargebacks, and credit memos?",
            topic="refund",
            keywords=("refund", "chargeback", "credit memo"),
        ),
        Question(
            question_id="Q4",
            text="Which records describe foreign-exchange rates and currency conversion?",
            topic="foreign-exchange",
            keywords=("fx rate", "currency", "conversion"),
        ),
        Question(
            question_id="Q5",
            text="Which records cover travel expenses, flights, and per diem?",
            topic="travel",
            keywords=("travel", "flight", "per diem"),
        ),
        Question(
            question_id="Q6",
            text="Which records are about subscription renewals and license seats?",
            topic="subscription",
            keywords=("subscription", "renewal", "license"),
        ),
    ]
    return Corpus(documents=documents, questions=questions)
