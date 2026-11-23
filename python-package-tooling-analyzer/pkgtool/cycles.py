"""Dependency-cycle detection over an :class:`ImportGraph`.

Uses Tarjan's strongly-connected-components algorithm: any component
with more than one module — or a module that imports itself — is a cycle.
Each reported cycle is a closed loop of module names in import order.
"""

from __future__ import annotations

from pkgtool.graph import ImportGraph


def _tarjan(graph: ImportGraph) -> list[list[str]]:
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: set[str] = set()
    result: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(graph.edges.get(v, ())):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            result.append(sorted(component))

    for v in sorted(graph.modules):
        if v not in index:
            strongconnect(v)
    return result


def find_cycles(graph: ImportGraph) -> list[list[str]]:
    """Return each dependency cycle as an ordered loop of module names.

    A cycle ``[a, b, c]`` means a imports b, b imports c, c imports a.
    Self-imports are returned as ``[a]``.
    """
    cycles: list[list[str]] = []
    for component in _tarjan(graph):
        if len(component) > 1:
            # Order the component into a loop by following edges.
            ordered = [component[0]]
            seen = {component[0]}
            while len(ordered) < len(component):
                nxt = next(
                    (d for d in sorted(graph.edges.get(ordered[-1], ())) if d in component and d not in seen),
                    None,
                )
                if nxt is None:
                    break
                ordered.append(nxt)
                seen.add(nxt)
            cycles.append(ordered)
        elif len(component) == 1:
            mod = component[0]
            if mod in graph.edges.get(mod, set()):
                cycles.append([mod])
    return sorted(cycles)
