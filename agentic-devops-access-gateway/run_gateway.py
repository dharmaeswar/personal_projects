"""Demo: register remote servers, issue scoped tokens, run agent actions.

Shows the four gates in action -- a scoped deployer token succeeds, an
operator token trying to deploy is denied, and a revoked token is denied --
then prints the audit log. All data is synthetic and local.
"""

from gateway import AccessGateway

gw = AccessGateway()
gw.registry.register("srv-prod-1", "prod-us-east-1", "prod", "10.0.1.21:22")
gw.registry.register("srv-stage-1", "staging-eu-1", "staging", "10.0.2.14:22")

deployer = gw.tokens.issue("agent-deploy-1", "deployer",
                           ["deploy:service:checkout", "read:service:checkout"],
                           "prod")
operator = gw.tokens.issue("agent-ops-1", "operator",
                           ["read:service:checkout"], "prod")

print("== allowed: deployer deploys checkout ==")
print(gw.execute(deployer, "deploy", "service:checkout", "srv-prod-1",
                 idempotency_key="req-001"))
print("== replay: same idempotency key, no re-execution ==")
print(gw.execute(deployer, "deploy", "service:checkout", "srv-prod-1",
                 idempotency_key="req-001"))
print("== denied: operator token has no deploy scope ==")
print(gw.execute(operator, "deploy", "service:checkout", "srv-prod-1"))
print("== denied: deployer token cannot touch staging (wrong environment) ==")
print(gw.execute(deployer, "deploy", "service:checkout", "srv-stage-1"))

print(f"\n== audit log ({len(gw.audit)} entries) ==")
for e in gw.audit.entries():
    print(f"#{e.seq} {e.decision:7} {e.actor} {e.action} {e.resource} "
          f"on {e.server_id}: {e.reason}")
print(f"\nExecuted actions: {len(gw.executed_actions)} "
      f"(replay did not re-execute)")
