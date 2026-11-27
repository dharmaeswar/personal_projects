"""Human-in-the-loop feedback: accept/reject on answers, with an audit log.

A scientist reviews an answer and accepts it or rejects it with a reason.
Accepted answers up-weight the graph edges behind them; rejected answers
down-weight those edges, so the next retrieval run ranks the disputed
evidence lower. Feedback never deletes an edge or rewrites a document —
it only changes retrieval weight, and every change is recorded in the
audit log with the question, the verdict, and the reason.
"""

import json


class FeedbackLog:
    """Append-only feedback record plus edge reweighting on a graph."""

    def __init__(self):
        self.entries = []

    def record(self, question_id, verdict, reason, edge_keys):
        """Log one review. verdict is 'accept' or 'reject'."""
        if verdict not in ("accept", "reject"):
            raise ValueError("verdict must be 'accept' or 'reject'")
        entry = {"question_id": question_id, "verdict": verdict,
                 "reason": reason, "edges": sorted(edge_keys)}
        self.entries.append(entry)
        return entry

    def apply_to(self, graph):
        """Apply all logged feedback to the graph's edge weights."""
        for entry in self.entries:
            factor = 1.25 if entry["verdict"] == "accept" else 0.5
            for edge in graph.edges:
                key = (edge["subj"], edge["relation"], edge["obj"])
                if key in entry["edges"]:
                    edge["weight"] = round(edge["weight"] * factor, 3)
        return graph

    def audit_text(self):
        lines = ["Feedback audit log", "-" * 40]
        for e in self.entries:
            edges = "; ".join(f"{s} {r} {o}" for s, r, o in e["edges"])
            lines.append(f"{e['question_id']} {e['verdict']}: {e['reason']} "
                         f"(edges: {edges or 'none'})")
        return "\n".join(lines) + "\n"

    def to_json(self):
        return json.dumps(self.entries, indent=2)
