"""The agent: plan tool calls, run them inside a step budget, and keep a
human in the loop for anything that leaves the system.

Planning is keyword-based and deterministic (a stand-in for an LLM planner):
- every request starts with a knowledge-base search;
- requests naming a patient also pull de-identified patient context;
- "summary" requests draft a summary for clinician review;
- urgent symptoms ("chest pain", "breathless", "confusion") or a referral
  request draft an escalation, which only goes out with approval;
- "send"/"message" requests draft a patient message, sent only with approval.

The agent never sends or escalates without approval, never exceeds the step
budget, and every decision lands in the audit log.
"""

from .audit import AuditLog
from .tools import ToolError, ToolServer

MAX_STEPS = 6
URGENT_TERMS = ("chest pain", "breathless", "shortness of breath", "confusion")


class Agent:
    def __init__(self, tools=None, audit=None):
        self.tools = tools or ToolServer()
        self.audit = audit or AuditLog()

    def _plan(self, request, patient_id):
        lowered = request.lower()
        steps = [("search_kb", {"query": request, "top_k": 3})]
        if patient_id:
            steps.append(("get_patient_context", {"patient_id": patient_id}))
        if "summary" in lowered and patient_id:
            steps.append(
                ("draft_summary", {"patient_id": patient_id, "topic": request})
            )
        urgent = any(term in lowered for term in URGENT_TERMS)
        if urgent or "referral" in lowered or "escalate" in lowered:
            reason = "urgent symptoms reported" if urgent else "referral requested"
            steps.append(
                (
                    "escalate_to_clinician",
                    {"patient_id": patient_id, "reason": reason},
                )
            )
        if ("send" in lowered or "message" in lowered) and patient_id:
            steps.append(
                (
                    "send_message",
                    {
                        "patient_id": patient_id,
                        "message": f"Follow-up on: {request}",
                    },
                )
            )
        return steps

    def run(self, request, patient_id=None, approve_send=False):
        self.audit.append("agent", "request_received", request)
        steps = self._plan(request, patient_id)[:MAX_STEPS]
        tools_used = []
        answer_parts = []
        pending_approval = False
        escalated = False
        sent = False
        for tool, args in steps:
            if tool in ("escalate_to_clinician", "send_message"):
                args = dict(args, approved=approve_send)
            try:
                result = self.tools.call(tool, **args)
            except ToolError as exc:
                self.audit.append("agent", f"{tool}_denied", str(exc))
                if "requires human approval" in str(exc):
                    pending_approval = True
                    answer_parts.append(
                        "Drafted and held for clinician approval: "
                        f"{tool.replace('_', ' ')}."
                    )
                else:
                    answer_parts.append(f"Could not run {tool}: {exc}.")
                continue
            tools_used.append(tool)
            self.audit.append("agent", f"{tool}_ok", str(result)[:300])
            if tool == "search_kb" and result:
                titles = "; ".join(hit["title"] for hit in result)
                answer_parts.append(f"Guidance found: {titles}.")
            elif tool == "get_patient_context":
                answer_parts.append(
                    "Patient context reviewed: "
                    + ", ".join(result["conditions"])
                    + "."
                )
            elif tool == "draft_summary":
                answer_parts.append("Draft summary ready for clinician review.")
            elif tool == "escalate_to_clinician":
                escalated = True
                answer_parts.append("Escalated to the on-call clinician.")
            elif tool == "send_message":
                sent = True
                answer_parts.append("Message sent after clinician approval.")
        self.audit.append(
            "agent",
            "request_completed",
            f"tools={','.join(tools_used)} escalated={escalated} sent={sent}",
        )
        return {
            "answer": " ".join(answer_parts) or "No guidance found.",
            "tools_used": tools_used,
            "escalated": escalated,
            "sent": sent,
            "pending_approval": pending_approval,
            "audit": self.audit.to_list(),
            "trace": list(self.tools.trace),
        }
