"""Fintech Agent Reconciliation Platform.

MCP-server-shaped finance agents in the shape of the Twitch SWE II,
Fintech role: Bedrock-style agents that automate Finance work —
reconciliations, reporting, variance analysis, and payouts — behind MCP
servers with OAuth 2.0 / OIDC scopes, guardrails, human-in-the-loop
approvals, evaluation, and auditability, on AWS-native infrastructure
(Lambda-shaped handlers, DynamoDB-shaped store, SQS-shaped queues).

All data is synthetic and local. Nothing here claims production use or
real Bedrock/MCP calls: the "LLM" is a fixed deterministic planner, so
every run is reproducible with no model cost.
"""

from .agent import FinanceAgent
from .ledger import BankLine, LedgerEntry, Reconciler
from .mcp import McpServer
from .observability import AuditLog, Metrics

__all__ = ["FinanceAgent", "BankLine", "LedgerEntry", "Reconciler",
           "McpServer", "AuditLog", "Metrics"]
