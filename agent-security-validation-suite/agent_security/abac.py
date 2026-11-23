"""Attribute-based access control (ABAC) for identity services.

Models the shape of an identity directory service like the CARDS
attribute repository behind IAM: a consolidated attribute store for
principals and resources, plus a policy engine that decides
allow/deny from subject, resource, action, and environment
attributes. Fine-grained access control (FGAC) is enforced at the
field level: a caller allowed to read a resource may still be denied
individual sensitive fields.

Decisions are deny-by-default. Every decision records which policy
rule matched (or that none did), so a denial is explainable and an
allow is auditable. All data is synthetic and local.
"""

from dataclasses import dataclass, field


# Classification levels, lowest to highest.
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")


def _level(name):
    return CLASSIFICATIONS.index(name)


@dataclass(frozen=True)
class Subject:
    """A principal asking for access."""

    principal_id: str
    team: str
    clearance: str  # one of CLASSIFICATIONS
    employment_type: str = "employee"  # employee | contractor | service
    mfa: bool = False
    region: str = "us-east-1"


@dataclass(frozen=True)
class Resource:
    """A protected resource with attribute metadata."""

    resource_id: str
    owner_team: str
    classification: str  # one of CLASSIFICATIONS
    region: str = "us-east-1"
    sensitive_fields: frozenset = frozenset()
    stale_attributes: bool = False


@dataclass(frozen=True)
class PolicyRule:
    """One ABAC rule. All listed conditions must hold to match."""

    name: str
    action: str  # e.g. "read", "write", or "*" for any action
    effect: str  # "allow" or "deny"
    min_clearance: str = None
    same_team: bool = False
    require_mfa: bool = False
    max_classification: str = None
    employees_only: bool = False
    same_region: bool = False


@dataclass
class Decision:
    allowed: bool
    rule: str
    reason: str
    fields_denied: tuple = ()


# Default policy set, evaluated in order. Explicit denies win over
# later allows because the first matching rule decides.
DEFAULT_RULES = [
    PolicyRule("deny-stale-attributes", "*", "deny"),
    PolicyRule("deny-restricted-to-contractors", "*", "deny",
               employees_only=True),
    PolicyRule("allow-same-team-read", "read", "allow",
               same_team=True, max_classification="confidential"),
    PolicyRule("allow-cross-team-read", "read", "allow",
               min_clearance="confidential", max_classification="internal"),
    PolicyRule("allow-same-team-write", "write", "allow",
               same_team=True, require_mfa=True,
               max_classification="confidential"),
]


class AttributeRepository:
    """Consolidated attribute store (CARDS-style).

    Holds subject and resource attributes in one place so the policy
    engine reads a single consistent snapshot. Attributes flagged
    stale (source system has not refreshed them) force a deny until
    they are refreshed, instead of deciding on outdated data.
    """

    def __init__(self):
        self.subjects = {}
        self.resources = {}

    def add_subject(self, subject):
        self.subjects[subject.principal_id] = subject

    def add_resource(self, resource):
        self.resources[resource.resource_id] = resource

    def get_subject(self, principal_id):
        return self.subjects.get(principal_id)

    def get_resource(self, resource_id):
        return self.resources.get(resource_id)

    def refresh(self, resource_id):
        """Mark a resource's attributes fresh after a source refresh."""
        resource = self.resources.get(resource_id)
        if resource is None:
            return False
        self.resources[resource_id] = Resource(
            resource_id=resource.resource_id,
            owner_team=resource.owner_team,
            classification=resource.classification,
            region=resource.region,
            sensitive_fields=resource.sensitive_fields,
            stale_attributes=False,
        )
        return True


def _rule_matches(rule, subject, resource, action):
    if rule.action != "*" and rule.action != action:
        return False
    if rule.min_clearance is not None:
        if _level(subject.clearance) < _level(rule.min_clearance):
            return False
    if rule.max_classification is not None:
        if _level(resource.classification) > _level(rule.max_classification):
            return False
    if rule.same_team and subject.team != resource.owner_team:
        return False
    if rule.require_mfa and not subject.mfa:
        return False
    if rule.employees_only and subject.employment_type != "employee":
        return False
    if rule.same_region and subject.region != resource.region:
        return False
    return True


class PolicyEngine:
    """Evaluates ABAC requests against an ordered rule set."""

    def __init__(self, rules=None, repository=None):
        self.rules = list(rules if rules is not None else DEFAULT_RULES)
        self.repository = repository or AttributeRepository()

    def decide(self, subject, resource, action, requested_fields=()):
        """Return a Decision for (subject, resource, action).

        requested_fields lists the resource fields the caller wants;
        sensitive fields are denied unless the caller is on the owning
        team with MFA.
        """
        if resource.stale_attributes:
            return Decision(False, "deny-stale-attributes",
                            "resource attributes are stale; refresh required")
        if subject.employment_type != "employee" and \
                resource.classification == "restricted":
            return Decision(False, "deny-restricted-to-contractors",
                            "restricted resources are employees only")
        if _level(subject.clearance) < _level(resource.classification):
            return Decision(False, "clearance-below-classification",
                            "clearance %s is below resource classification %s"
                            % (subject.clearance, resource.classification))
        for rule in self.rules:
            if rule.name in ("deny-stale-attributes",
                             "deny-restricted-to-contractors"):
                continue
            if _rule_matches(rule, subject, resource, action):
                if rule.effect == "deny":
                    return Decision(False, rule.name,
                                    "matched deny rule %s" % rule.name)
                denied = tuple(
                    f for f in requested_fields
                    if f in resource.sensitive_fields
                    and not (subject.team == resource.owner_team
                             and subject.mfa)
                )
                return Decision(True, rule.name,
                                "matched allow rule %s" % rule.name,
                                fields_denied=denied)
        return Decision(False, "default-deny",
                        "no policy rule matched; deny by default")

    def decide_by_id(self, principal_id, resource_id, action,
                     requested_fields=()):
        """Look attributes up in the repository, then decide."""
        subject = self.repository.get_subject(principal_id)
        resource = self.repository.get_resource(resource_id)
        if subject is None:
            return Decision(False, "unknown-subject",
                            "no attributes for principal %s" % principal_id)
        if resource is None:
            return Decision(False, "unknown-resource",
                            "no attributes for resource %s" % resource_id)
        return self.decide(subject, resource, action, requested_fields)


def run_abac_suite():
    """Deterministic scenario set; returns (rows, allowed, denied)."""
    repo = AttributeRepository()
    repo.add_subject(Subject("alice", "identity", "confidential",
                             mfa=True))
    repo.add_subject(Subject("bob", "payments", "confidential", mfa=True))
    repo.add_subject(Subject("carol", "identity", "internal"))
    repo.add_subject(Subject("dave", "identity", "confidential",
                             employment_type="contractor", mfa=True))
    repo.add_subject(Subject("svc-sync", "identity", "restricted",
                             employment_type="service", mfa=True))
    repo.add_resource(Resource("cards:attrs:alice", "identity",
                               "confidential",
                               sensitive_fields=frozenset({"ssn", "salary"})))
    repo.add_resource(Resource("cards:attrs:bob", "payments", "internal"))
    repo.add_resource(Resource("cards:keys:root", "identity", "restricted"))
    repo.add_resource(Resource("cards:attrs:stale", "identity", "internal",
                               stale_attributes=True))
    engine = PolicyEngine(repository=repo)
    scenarios = [
        # (principal, resource, action, fields, expect_allowed)
        ("alice", "cards:attrs:alice", "read", ("name", "ssn"), True),
        ("alice", "cards:attrs:alice", "write", (), True),
        ("alice", "cards:attrs:bob", "read", ("name",), True),
        ("bob", "cards:attrs:alice", "read", ("name",), False),
        ("bob", "cards:attrs:alice", "read", ("name", "ssn"), False),
        ("carol", "cards:attrs:alice", "read", ("name",), False),
        ("carol", "cards:attrs:alice", "write", (), False),
        ("dave", "cards:keys:root", "read", (), False),
        ("svc-sync", "cards:keys:root", "read", (), False),
        ("alice", "cards:attrs:stale", "read", (), False),
        ("mallory", "cards:attrs:alice", "read", (), False),
        ("alice", "cards:attrs:missing", "read", (), False),
        ("bob", "cards:attrs:bob", "write", (), True),
    ]
    rows = []
    for principal, resource, action, fields, expected in scenarios:
        decision = engine.decide_by_id(principal, resource, action, fields)
        rows.append({
            "principal": principal,
            "resource": resource,
            "action": action,
            "allowed": decision.allowed,
            "expected": expected,
            "passed": decision.allowed == expected,
            "rule": decision.rule,
            "fields_denied": list(decision.fields_denied),
        })
    allowed = sum(1 for r in rows if r["allowed"])
    return rows, allowed, len(rows) - allowed
