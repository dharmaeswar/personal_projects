"""Credit Review Data Quality & BI toolkit.

Portfolio project for the Capital One Principal Associate, Data Analyst -
Credit Review role. It covers the three work types in that job description:

- Innovation: mine a credit-review data set and build a self-service
  reporting capability on top of it.
- Business Intelligence: metrics and dashboards on review findings,
  cycle times, overdue reviews and rating migration.
- Data Management: data-quality monitoring (completeness, uniqueness,
  validity, referential integrity), metadata, lineage and business
  definitions, plus data-access governance.

All data is synthetic and seeded. No real bank, customer, or loan data is
used, and nothing here is a claim about any real institution.
"""

from .data import build_dataset
from .quality import run_quality_checks
from .governance import Catalog, AccessGovernor
from .metrics import build_dashboard

__all__ = ["build_dataset", "run_quality_checks", "Catalog", "AccessGovernor", "build_dashboard"]
