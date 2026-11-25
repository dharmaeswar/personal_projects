"""Forward-deployed governed data integration for AI systems.

A data-owner toolkit for an Advanced Forward Engineering delivery pod: it
ingests client and legacy data (Postgres dumps, Oracle-style extracts, a
paginated REST API), enforces data contracts, transforms records into a
canonical governed model, records lineage, applies RBAC + masking, detects
schema drift and quarantines bad rows, and serves retrieval (search +
embeddings-style ranking) and a feature store snapshot to the AI system.

All data is synthetic and seeded. Nothing here describes real EY, client,
tax, or financial data, and nothing ran in production.
"""

from .sources import SourceAdapter, PostgresDumpAdapter, OracleExtractAdapter, RestApiAdapter
from .contracts import DataContract, ContractViolation
from .quality import QualityReport, check_rows, detect_schema_drift

__all__ = [
    "SourceAdapter",
    "PostgresDumpAdapter",
    "OracleExtractAdapter",
    "RestApiAdapter",
    "DataContract",
    "ContractViolation",
    "QualityReport",
    "check_rows",
    "detect_schema_drift",
]
