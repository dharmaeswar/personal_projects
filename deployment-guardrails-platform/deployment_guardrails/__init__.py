"""Deployment guardrails platform.

A local model of a platform-wide deployment policy system: services
declare deployment templates, a policy engine validates each template
against shared guardrails, a fleet view tracks rollout status and
safety scores, every decision is written to an audit log, and an
on-call helper routes alerts and builds keep-the-lights-on checklists.

All data is synthetic and local. No real services, deployments, or
production traffic are involved.
"""

from deployment_guardrails.templates import DeploymentTemplate, Registry
from deployment_guardrails.policies import evaluate_template

__all__ = ["DeploymentTemplate", "Registry", "evaluate_template"]
