"""Agent skills registry for the partner-data platform.

An agent skill is a named, versioned capability an AI agent can invoke on
behalf of an ads partner: it declares its inputs, the data scopes it needs,
and a risk level. Medium- and high-risk skills need an explicit human
approval before they run; low-risk skills auto-approve. Every invocation is
recorded in an audit log so a partner request can be replayed end to end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RISK_LEVELS = ("low", "medium", "high")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")


@dataclass
class Skill:
    """One agent skill: what it does, what it needs, how risky it is."""

    name: str
    version: str
    description: str
    input_schema: dict
    required_scopes: list
    risk: str = "low"
    owner: str = "partner-platform"

    def validate(self) -> list:
        """Return a list of validation problems; empty means the skill is OK."""
        problems = []
        if not NAME_RE.match(self.name):
            problems.append(
                f"skill name {self.name!r} must be lowercase snake_case, 3-48 chars"
            )
        if not self.version or not re.match(r"^\d+\.\d+\.\d+$", self.version):
            problems.append(f"skill {self.name!r} version must be semver (x.y.z)")
        if not self.description or len(self.description) < 20:
            problems.append(f"skill {self.name!r} needs a description of 20+ chars")
        if not isinstance(self.input_schema, dict) or not self.input_schema:
            problems.append(f"skill {self.name!r} needs a non-empty input schema")
        for field_name, field_type in self.input_schema.items():
            if field_type not in ("string", "number", "boolean", "string_list"):
                problems.append(
                    f"skill {self.name!r} field {field_name!r} has unsupported "
                    f"type {field_type!r}"
                )
        if self.risk not in RISK_LEVELS:
            problems.append(f"skill {self.name!r} risk must be one of {RISK_LEVELS}")
        if not self.required_scopes:
            problems.append(f"skill {self.name!r} must declare at least one scope")
        return problems


@dataclass
class Invocation:
    """One recorded skill invocation, for the audit log."""

    skill_name: str
    inputs: dict
    approved: bool
    approved_by: str | None
    result: str


class SkillRegistry:
    """Registry of agent skills, with lookup, validation and invocation."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self.invocations: list[Invocation] = []

    def register(self, skill: Skill) -> None:
        problems = skill.validate()
        if problems:
            raise ValueError("; ".join(problems))
        if skill.name in self._skills:
            raise ValueError(f"skill {skill.name!r} is already registered")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_names(self) -> list:
        return sorted(self._skills)

    def invoke(self, name: str, inputs: dict, approved_by: str | None = None) -> Invocation:
        """Invoke a skill, enforcing the approval gate for risky skills."""
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"unknown skill {name!r}")
        missing = [f for f in skill.input_schema if f not in inputs]
        if missing:
            raise ValueError(f"skill {name!r} missing inputs: {missing}")
        if skill.risk in ("medium", "high") and approved_by is None:
            invocation = Invocation(name, inputs, False, None, "denied: approval required")
            self.invocations.append(invocation)
            return invocation
        result = f"ran {name} v{skill.version} with {len(inputs)} inputs"
        invocation = Invocation(name, inputs, True, approved_by, result)
        self.invocations.append(invocation)
        return invocation
