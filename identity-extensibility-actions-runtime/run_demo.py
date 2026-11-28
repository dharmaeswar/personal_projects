"""End-to-end demo: two tenants, three triggers, isolation enforced.

Tenant Acme runs a post-login action that adds a custom claim and a
pre-token-issuance action that denies tokens for blocked scopes.
Tenant Globex runs a post-login action that times out (too many steps
for its op budget) — post-login is fail-open, so the login still
succeeds and the failure is audited. A cross-tenant secret read is
refused outright. Prints the resulting claims, metrics and audit chain.
"""

from actions_runtime import ActionsService, AuthEvent, Trigger
from actions_runtime.actions import Action
from actions_runtime.k8s import render_manifests


def main() -> None:
    svc = ActionsService(op_budget=100)
    svc.create_tenant("acme", "Acme Corp")
    svc.create_tenant("globex", "Globex Inc")
    svc.put_secret("acme", "tier-api-key", "acme-key-9f2c")

    svc.register_action(Action(
        action_id="acme-post-login", tenant_id="acme", name="Add tier claim",
        trigger=Trigger.POST_LOGIN,
        steps=[
            {"op": "read_secret", "name": "tier-api-key"},
            {"op": "cache_put", "key": "tier:u123", "value": "enterprise"},
            {"op": "set_claim", "key": "https://acme.example/tier", "value": "enterprise"},
            {"op": "log", "message": "tier claim added for enterprise user"},
        ],
    ))
    svc.deploy_action("acme", "acme-post-login")

    svc.register_action(Action(
        action_id="acme-pre-token", tenant_id="acme", name="Block bad scopes",
        trigger=Trigger.PRE_TOKEN_ISSUANCE,
        steps=[
            {"op": "set_claim", "key": "scope_checked", "value": "true"},
            {"op": "deny", "reason": "requested scope 'admin:write' is not granted"},
        ],
    ))
    svc.deploy_action("acme", "acme-pre-token")

    svc.register_action(Action(
        action_id="globex-slow", tenant_id="globex", name="Slow analytics",
        trigger=Trigger.POST_LOGIN,
        steps=[{"op": "loop", "count": 120,
                "steps": [{"op": "log", "message": "analytics tick"}]}],
    ))
    svc.deploy_action("globex", "globex-slow")

    login = svc.invoke(AuthEvent(
        tenant_id="acme", user_id="u123",
        connection="Username-Password-Authentication",
        trigger=Trigger.POST_LOGIN,
    ))
    print("Acme post-login denied:", login.denied)
    print("Acme post-login claims:", login.event.claims)
    print("Acme action logs:", login.action_results[0].logs)

    token = svc.invoke(AuthEvent(
        tenant_id="acme", user_id="u123",
        connection="Username-Password-Authentication",
        trigger=Trigger.PRE_TOKEN_ISSUANCE,
    ))
    print("Acme pre-token denied:", token.denied, "| reason:", token.deny_reason)

    globex = svc.invoke(AuthEvent(
        tenant_id="globex", user_id="g9",
        connection="google-oauth2", trigger=Trigger.POST_LOGIN,
    ))
    slow = globex.action_results[0]
    print("Globex login denied:", globex.denied, "| action timed out:", slow.timed_out,
          "| ops used:", slow.ops_used)

    try:
        svc.deploy_action("globex", "acme-post-login")
    except ValueError as exc:
        print("Cross-tenant deploy refused:", exc)

    from actions_runtime.tenancy import check_same_tenant
    try:
        check_same_tenant("acme", "globex")
    except PermissionError as exc:
        print("Cross-tenant access refused:", exc)

    print("Metrics acme-post-login:", svc.runner.metrics["acme-post-login"])
    print("Metrics globex-slow:", svc.runner.metrics["globex-slow"])
    print("Audit entries:", len(svc.audit.entries),
          "| chain valid:", svc.audit.verify_chain())

    # Authorization modeling (OpenFGA-style): u123 is a viewer of the
    # Acme report, so the union rewrite makes them an editor and admin
    # too; a stranger gets nothing, and a check for an unknown tenant
    # is refused outright.
    svc.authz.write_tuple("user:u123", "viewer", "resource:report-7")
    print("Authz u123 viewer report-7:",
          svc.authorize("acme", "user:u123", "viewer", "resource:report-7")["allowed"])
    print("Authz u123 admin report-7 (via editor rewrite):",
          svc.authorize("acme", "user:u123", "admin", "resource:report-7")["allowed"])
    print("Authz stranger viewer report-7:",
          svc.authorize("acme", "user:other", "viewer", "resource:report-7")["allowed"])
    print("Authz objects u123 can view:",
          svc.authz.list_objects("user:u123", "viewer", "resource"))

    print("Health:", svc.health())
    manifests = render_manifests()
    print("K8s manifests:", sorted(manifests),
          "| deployment replicas line present:",
          "replicas: 3" in manifests["deployment.yaml"])


if __name__ == "__main__":
    main()
