"""Tool server: the only way the agent touches data or takes action.

Every tool call is validated against its schema and traced (tool, args,
latency, outcome). Read tools run freely. Write tools -- sending a message
or escalating to a clinician -- need explicit human approval; without it the
call is denied and the denial is traced. No tool returns PHI: patient
context is de-identified by design (conditions and medications only).
"""

import time

from .kb import PATIENTS
from .phi import redact
from .retrieval import search
from .rwd import (build_cohort, data_quality, generate_claims,
                 patient_journey, treatment_patterns, utilization_summary)


class ToolError(Exception):
    pass


def _require(args, *names):
    for name in names:
        if name not in args or args[name] is None or args[name] == "":
            raise ToolError(f"missing required argument: {name}")


class ToolServer:
    def __init__(self):
        self.trace = []

    def _record(self, tool, args, outcome, started):
        safe_args, _ = redact(str(args))
        self.trace.append(
            {
                "tool": tool,
                "args": safe_args,
                "outcome": outcome,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )

    def call(self, tool, **args):
        started = time.monotonic()
        handler = getattr(self, f"_tool_{tool}", None)
        if handler is None:
            self._record(tool, args, "error: unknown tool", started)
            raise ToolError(f"unknown tool: {tool}")
        try:
            result = handler(**args)
        except ToolError as exc:
            self._record(tool, args, f"error: {exc}", started)
            raise
        self._record(tool, args, "ok", started)
        return result

    def _tool_search_kb(self, query, top_k=3):
        _require({"query": query}, "query")
        hits = search(query, top_k=top_k)
        return [
            {
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "snippet": doc["text"][:220],
                "score": score,
            }
            for doc, score in hits
        ]

    def _tool_get_patient_context(self, patient_id):
        _require({"patient_id": patient_id}, "patient_id")
        patient = PATIENTS.get(patient_id)
        if patient is None:
            raise ToolError(f"unknown patient_id: {patient_id}")
        return {
            "patient_id": patient_id,
            "conditions": list(patient["conditions"]),
            "medications": list(patient["medications"]),
            "last_visit": patient["last_visit"],
            "risk_flags": list(patient["risk_flags"]),
        }

    def _tool_draft_summary(self, patient_id, topic):
        _require(
            {"patient_id": patient_id, "topic": topic}, "patient_id", "topic"
        )
        context = self._tool_get_patient_context(patient_id)
        guidance = self._tool_search_kb(topic, top_k=2)
        lines = [
            f"Draft summary for {patient_id} on {topic}.",
            "Conditions: " + ", ".join(context["conditions"]) + ".",
            "Medications: " + ", ".join(context["medications"]) + ".",
        ]
        if context["risk_flags"]:
            lines.append("Risk flags: " + "; ".join(context["risk_flags"]) + ".")
        for hit in guidance:
            lines.append(f"Guidance ({hit['doc_id']}): {hit['snippet']}")
        lines.append("DRAFT ONLY -- needs clinician review before it is sent.")
        return {"draft": " ".join(lines)}

    def _tool_escalate_to_clinician(self, patient_id, reason, approved=False):
        _require(
            {"patient_id": patient_id, "reason": reason},
            "patient_id",
            "reason",
        )
        if patient_id not in PATIENTS:
            raise ToolError(f"unknown patient_id: {patient_id}")
        if not approved:
            raise ToolError(
                "escalation requires human approval; draft saved, not sent"
            )
        return {
            "escalated": True,
            "patient_id": patient_id,
            "reason": reason,
            "status": "sent to on-call clinician",
        }

    def _tool_send_message(self, patient_id, message, approved=False):
        _require(
            {"patient_id": patient_id, "message": message},
            "patient_id",
            "message",
        )
        if patient_id not in PATIENTS:
            raise ToolError(f"unknown patient_id: {patient_id}")
        if not approved:
            raise ToolError(
                "sending a patient message requires human approval; "
                "draft saved, not sent"
            )
        return {
            "sent": True,
            "patient_id": patient_id,
            "message": message,
            "status": "delivered after clinician approval",
        }

    def _tool_analyze_rwd(self, condition=None, patient_id=None):
        """RWD analytics over synthetic claims-like records (demo data only)."""
        records = generate_claims()
        result = {
            "cohort": build_cohort(records, condition=condition),
            "treatment_patterns": treatment_patterns(records),
            "utilization": utilization_summary(records),
            "quality": data_quality(records),
        }
        if patient_id:
            result["journey"] = patient_journey(records, patient_id)
        return result
