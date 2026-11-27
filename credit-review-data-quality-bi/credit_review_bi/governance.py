"""Data-access governance: metadata catalog and role-based access.

The catalog records, for every governed data set, its owner team, source
system, sensitivity and retention window. The governor enforces who may
read what: analysts read Internal data, auditors read everything
read-only, and Restricted data needs an approved purpose. Nothing here
grants write access to source systems.
"""

from dataclasses import dataclass

SENSITIVITY_LEVELS = ("Public", "Internal", "Restricted")
ROLES = ("analyst", "auditor", "admin", "business")


@dataclass
class CatalogEntry:
    dataset: str
    owner: str
    source_system: str
    sensitivity: str
    retention_days: int
    business_definition: str = ""


class Catalog:
    """Metadata catalog for the credit-review data sets."""

    def __init__(self):
        self._entries = {}

    def register(self, entry: CatalogEntry):
        if entry.sensitivity not in SENSITIVITY_LEVELS:
            raise ValueError(f"unknown sensitivity: {entry.sensitivity}")
        self._entries[entry.dataset] = entry

    def get(self, dataset: str):
        return self._entries.get(dataset)

    def datasets(self):
        return sorted(self._entries)

    def restricted_datasets(self):
        return [d for d, e in self._entries.items() if e.sensitivity == "Restricted"]


def default_catalog() -> Catalog:
    catalog = Catalog()
    catalog.register(CatalogEntry(
        "loans", "Credit Review", "Loan Origination System", "Internal", 2555,
        "Reviewed loan portfolio with risk ratings."))
    catalog.register(CatalogEntry(
        "reviews", "Credit Review", "Review Workflow", "Internal", 2555,
        "Credit review records with outcomes and cycle times."))
    catalog.register(CatalogEntry(
        "findings", "Credit Review", "Review Workflow", "Internal", 2555,
        "Issues raised by reviews, with severity and status."))
    catalog.register(CatalogEntry(
        "borrower_pii", "Credit Review", "Loan Origination System", "Restricted", 365,
        "Borrower names and contact details. Restricted: no analyst access."))
    return catalog


class AccessGovernor:
    """Decides read access by role, sensitivity and purpose."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self._log = []

    def can_read(self, role: str, dataset: str, purpose: str = "") -> bool:
        entry = self.catalog.get(dataset)
        allowed = False
        reason = ""
        if role not in ROLES:
            reason = f"unknown role: {role}"
        elif entry is None:
            reason = f"dataset not in catalog: {dataset}"
        elif role == "admin":
            allowed, reason = True, "admin: full access"
        elif entry.sensitivity == "Restricted":
            allowed = role == "auditor" and purpose == "audit"
            reason = "restricted: auditor + audit purpose only" if allowed else \
                "restricted: auditor + audit purpose only"
        elif role in ("analyst", "auditor", "business"):
            allowed, reason = True, f"{role}: {entry.sensitivity} data readable"
        self._log.append({"role": role, "dataset": dataset, "purpose": purpose,
                          "allowed": allowed, "reason": reason})
        return allowed

    def access_log(self):
        return list(self._log)
