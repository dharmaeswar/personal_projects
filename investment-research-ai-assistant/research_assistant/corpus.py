"""Seeded synthetic corpus of investment research notes (fictional companies)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Document:
    doc_id: str
    company: str
    doc_type: str  # earnings_note | filing_excerpt | analyst_note | risk_memo
    date: str
    section: str
    text: str


CORPUS = [
    Document(
        doc_id="ACME-10K-2026-Q3",
        company="Acme Industrial Holdings",
        doc_type="filing_excerpt",
        date="2026-10-28",
        section="Segment results",
        text=(
            "Acme Industrial Holdings reported third-quarter revenue of $4.2 billion, up 6 percent "
            "year over year, driven by the automation segment, which grew 14 percent. Operating "
            "margin expanded to 18.4 percent from 17.1 percent a year earlier as input costs eased. "
            "Free cash flow was $610 million, and the company repurchased $200 million of shares "
            "in the quarter. Management guided full-year revenue growth of 5 to 7 percent."
        ),
    ),
    Document(
        doc_id="ACME-EARN-Q3-2026",
        company="Acme Industrial Holdings",
        doc_type="earnings_note",
        date="2026-10-28",
        section="Management commentary",
        text=(
            "On the earnings call, Acme management said order backlog rose to $9.8 billion, with "
            "automation orders up 22 percent. The CEO noted that supply-chain lead times have "
            "normalized to pre-2024 levels. Capital spending for the year is expected to be "
            "$450 million, focused on the Ohio plant expansion. Management declined to give "
            "fourth-quarter margin guidance, citing raw-material price uncertainty."
        ),
    ),
    Document(
        doc_id="BEACON-AN-2026-11",
        company="Beacon Health Systems",
        doc_type="analyst_note",
        date="2026-11-04",
        section="Initiation",
        text=(
            "Beacon Health Systems operates 41 hospitals and 210 outpatient clinics across the "
            "southeastern United States. Same-facility admissions grew 3 percent in the latest "
            "quarter while labor cost per adjusted admission fell 2 percent. The analyst note "
            "highlights payer-mix improvement, with commercial insurance now 38 percent of "
            "revenue, up from 35 percent a year ago. Net leverage stands at 3.1 times EBITDA."
        ),
    ),
    Document(
        doc_id="BEACON-10K-2026-Q2",
        company="Beacon Health Systems",
        doc_type="filing_excerpt",
        date="2026-08-12",
        section="Liquidity",
        text=(
            "Beacon Health Systems held $840 million of cash and $1.2 billion of undrawn revolver "
            "capacity at quarter end. Total debt was $6.4 billion, with no maturities before 2028. "
            "The company refinanced $900 million of term loans in June, extending the maturity to "
            "2031 and cutting the coupon by 75 basis points. Covenant headroom remains ample."
        ),
    ),
    Document(
        doc_id="NORTHWIND-EARN-Q3-2026",
        company="Northwind Energy Partners",
        doc_type="earnings_note",
        date="2026-11-02",
        section="Production update",
        text=(
            "Northwind Energy Partners produced 142,000 barrels of oil equivalent per day in the "
            "third quarter, up 4 percent sequentially. Realized prices averaged $71 per barrel, "
            "down from $78 a year earlier. The company cut its 2026 capital budget by $150 million "
            "to $1.1 billion and raised its dividend by 5 percent to $0.42 per share per quarter."
        ),
    ),
    Document(
        doc_id="NORTHWIND-RISK-2026",
        company="Northwind Energy Partners",
        doc_type="risk_memo",
        date="2026-09-18",
        section="Commodity exposure",
        text=(
            "Northwind hedges roughly 60 percent of next-twelve-months oil production using "
            "collars with a $60 floor and an $85 ceiling. Unhedged volumes remain exposed to "
            "spot price moves. The risk memo notes that a sustained $10 per barrel price decline "
            "would reduce annual operating cash flow by about $180 million before hedges."
        ),
    ),
    Document(
        doc_id="HELIX-AN-2026-10",
        company="Helix Software Group",
        doc_type="analyst_note",
        date="2026-10-21",
        section="Product update",
        text=(
            "Helix Software Group grew subscription revenue 21 percent year over year to "
            "$380 million, with net revenue retention of 118 percent. The company added 240 "
            "enterprise customers in the quarter and now serves 3,100 enterprise accounts. "
            "Gross margin on subscriptions is 82 percent. Management expects subscription "
            "growth of 18 to 20 percent next year, with operating margin of 24 to 26 percent."
        ),
    ),
    Document(
        doc_id="HELIX-10K-2026-Q3",
        company="Helix Software Group",
        doc_type="filing_excerpt",
        date="2026-10-30",
        section="R&D",
        text=(
            "Helix Software Group spent $210 million on research and development in the quarter, "
            "equal to 31 percent of revenue, up from 28 percent a year earlier. Headcount in "
            "engineering rose to 2,400. The filing discloses two material customer contracts "
            "signed in the quarter, each worth more than $25 million in annual recurring revenue."
        ),
    ),
    Document(
        doc_id="ACME-RISK-2026",
        company="Acme Industrial Holdings",
        doc_type="risk_memo",
        date="2026-09-02",
        section="Input costs",
        text=(
            "Acme's automation segment buys copper and specialty steel on spot contracts. A 10 "
            "percent rise in copper prices would add about $45 million to annual input costs. "
            "The risk memo notes the company holds no commodity hedges and passes through "
            "roughly half of input-cost moves to customers within two quarters."
        ),
    ),
    Document(
        doc_id="BEACON-EARN-Q3-2026",
        company="Beacon Health Systems",
        doc_type="earnings_note",
        date="2026-11-03",
        section="Outlook",
        text=(
            "Beacon Health Systems raised full-year adjusted EBITDA guidance to $1.45 billion to "
            "$1.50 billion from $1.38 billion to $1.44 billion. Management attributed the raise "
            "to stronger surgical volumes and lower contract-labor spending. The company expects "
            "capital spending of $520 million for the year, mostly for facility modernization."
        ),
    ),
    Document(
        doc_id="HELIX-EARN-Q3-2026",
        company="Helix Software Group",
        doc_type="earnings_note",
        date="2026-10-29",
        section="Guidance",
        text=(
            "Helix Software Group guided fourth-quarter subscription revenue of $395 million to "
            "$405 million. The CFO said the sales pipeline grew 18 percent year over year, with "
            "the largest deals in financial services. Churn among enterprise customers stayed "
            "below 4 percent annualized. The company ended the quarter with $1.1 billion in cash."
        ),
    ),
    Document(
        doc_id="NORTHWIND-10K-2026-Q3",
        company="Northwind Energy Partners",
        doc_type="filing_excerpt",
        date="2026-11-02",
        section="Reserves",
        text=(
            "Northwind Energy Partners reported proved reserves of 612 million barrels of oil "
            "equivalent, up 3 percent from year end. The reserve replacement ratio was 128 "
            "percent. Proved developed reserves are 71 percent of the total. The filing notes "
            "that 85 percent of proved reserves are in the Permian Basin."
        ),
    ),
]


def load_corpus():
    """Return the seeded corpus (a copy of the list)."""
    return list(CORPUS)
