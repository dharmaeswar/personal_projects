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
from .close_agent import CloseAgent
from .databricks_jobs import DatabricksJob, DataQualityCheck, JobTask
from .eval_framework import EvaluationFramework, GoldenCase
from .finance_api import FakeErpTransport, FinanceApiClient
from .finance_close import (CloseChecklist, CloseTask, arr_roll_forward,
                            billings_vs_revenue, consolidate,
                            forecast_variance)
from .finance_sql import FinanceWarehouse
from .ledger import BankLine, LedgerEntry, Reconciler
from .mcp import McpServer
from .observability import (AuditLog, CostTracker, Metrics,
                            StructuredLogger, Tracer)

__all__ = ["FinanceAgent", "CloseAgent", "BankLine", "LedgerEntry",
           "Reconciler", "McpServer", "AuditLog", "Metrics",
           "StructuredLogger", "Tracer", "CostTracker",
           "CloseChecklist", "CloseTask", "consolidate",
           "arr_roll_forward", "billings_vs_revenue",
           "forecast_variance", "FinanceWarehouse", "DatabricksJob",
           "DataQualityCheck", "JobTask", "FinanceApiClient",
           "FakeErpTransport", "EvaluationFramework", "GoldenCase"]
