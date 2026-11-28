"""Relationship-based authorization modeling and evaluation.

A small, self-contained model of the authorization layer a CIAM platform
needs when it replaces legacy authorization with a self-hosted OpenFGA
solution: an authorization model (types + relations) plus a tuple store,
evaluated with the same semantics OpenFGA documents:

- objects are typed, e.g. ``user:u1``, ``tenant:acme``,
  ``resource:report-7``;
- a relationship tuple ``(user, relation, object)`` says the user holds
  that relation on that object, e.g. ``user:u1 viewer resource:report-7``;
- a relation in the model is either a direct assignment or a rewrite —
  a union of other relations on the same object (a "userset rewrite"),
  so ``editor`` can mean "direct editors plus everyone who is a
  ``viewer``", and ``admin`` can mean "direct admins plus ``editor``";
- ``check`` answers one question — does this user hold this relation on
  this object — with a recursion guard so a cyclic model cannot loop
  forever, and a depth cap so a deep rewrite chain fails closed instead
  of hanging the login path.

Groups (``group:eng``) can appear as users: a tuple granting a group a
relation on an object covers every member of that group, mirroring how
OpenFGA resolves ``group#member`` usersets.

Nothing here talks to a real OpenFGA server and no real user, tenant or
resource is named; all data is synthetic and local.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_REWRITE_DEPTH = 10


@dataclass(frozen=True)
class Tuple:
    """One relationship tuple: user holds relation on object."""

    user: str  # e.g. "user:u1" or "group:eng"
    relation: str  # e.g. "viewer"
    object: str  # e.g. "resource:report-7"


@dataclass
class RelationDef:
    """How one relation on one object type is resolved.

    ``kind="direct"``: only tuples with this exact relation count.
    ``kind="union"``: the relation also holds for anyone holding any of
    ``members`` on the same object (userset rewrite, e.g. editor =
    union(direct editors, viewer)).
    """

    kind: str = "direct"
    members: tuple[str, ...] = ()


@dataclass
class AuthorizationModel:
    """Type definitions: object type -> relation name -> definition."""

    type_definitions: dict[str, dict[str, RelationDef]] = field(default_factory=dict)

    def define(self, object_type: str, relation: str,
               kind: str = "direct", members: tuple[str, ...] = ()) -> None:
        if kind not in ("direct", "union"):
            raise ValueError(f"unknown relation kind: {kind}")
        self.type_definitions.setdefault(object_type, {})[relation] = RelationDef(kind, members)

    def definition_for(self, object_type: str, relation: str) -> RelationDef | None:
        return self.type_definitions.get(object_type, {}).get(relation)


class AuthorizationStore:
    """Tuple store + evaluator for one authorization model."""

    def __init__(self, model: AuthorizationModel | None = None) -> None:
        self.model = model or AuthorizationModel()
        self._tuples: set[Tuple] = set()
        # group -> member users, e.g. "group:eng" -> {"user:u1", "user:u2"}
        self._groups: dict[str, set[str]] = {}

    # -- writes ----------------------------------------------------------
    def write_tuple(self, user: str, relation: str, object: str) -> Tuple:
        tup = Tuple(user=user, relation=relation, object=object)
        self._tuples.add(tup)
        return tup

    def delete_tuple(self, user: str, relation: str, object: str) -> bool:
        tup = Tuple(user=user, relation=relation, object=object)
        if tup in self._tuples:
            self._tuples.remove(tup)
            return True
        return False

    def add_group_member(self, group: str, user: str) -> None:
        self._groups.setdefault(group, set()).add(user)

    def remove_group_member(self, group: str, user: str) -> bool:
        members = self._groups.get(group)
        if members and user in members:
            members.discard(user)
            return True
        return False

    # -- reads -----------------------------------------------------------
    def read_tuples(self, object: str | None = None,
                    relation: str | None = None,
                    user: str | None = None) -> list[Tuple]:
        return [t for t in sorted(self._tuples, key=lambda x: (x.object, x.relation, x.user))
                if (object is None or t.object == object)
                and (relation is None or t.relation == relation)
                and (user is None or t.user == user)]

    def check(self, user: str, relation: str, object: str) -> bool:
        """Does ``user`` hold ``relation`` on ``object``?"""
        return self._check(user, relation, object, seen=frozenset(), depth=0)

    def _check(self, user: str, relation: str, object: str,
               seen: frozenset, depth: int) -> bool:
        if depth > MAX_REWRITE_DEPTH:
            return False  # fail closed on an unexpectedly deep rewrite chain
        key = (user, relation, object)
        if key in seen:
            return False  # cyclic model: stop instead of looping forever
        seen = seen | {key}

        # Direct tuple for this user, or for a group the user belongs to.
        for tup in self._tuples:
            if tup.relation == relation and tup.object == object:
                if tup.user == user:
                    return True
                if tup.user in self._groups and user in self._groups[tup.user]:
                    return True

        # Userset rewrite: union of member relations on the same object.
        object_type = object.split(":", 1)[0] if ":" in object else object
        definition = self.model.definition_for(object_type, relation)
        if definition is not None and definition.kind == "union":
            return any(
                self._check(user, member, object, seen, depth + 1)
                for member in definition.members
            )
        return False

    def list_objects(self, user: str, relation: str, object_type: str) -> list[str]:
        """Every object of ``object_type`` the user holds ``relation`` on."""
        objects = {t.object for t in self._tuples
                   if t.object.startswith(object_type + ":")}
        return sorted(o for o in objects if self.check(user, relation, o))


def ciam_model() -> AuthorizationModel:
    """The model this CIAM platform ships: viewer < editor < admin.

    ``resource`` is the tenancy-scoped object (a report, a dashboard, a
    service config); ``tenant`` scopes who may act at all.
    """
    model = AuthorizationModel()
    model.define("resource", "viewer")
    model.define("resource", "editor", kind="union", members=("viewer",))
    model.define("resource", "admin", kind="union", members=("editor",))
    model.define("tenant", "member")
    model.define("tenant", "admin", kind="union", members=("member",))
    return model
