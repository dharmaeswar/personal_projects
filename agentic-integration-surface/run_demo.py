"""Demo: run the full integration flow for one legacy schema end to end."""

from integration_surface.context import CallerContext
from integration_surface.sdk import IntegrationClient


def main() -> None:
    ctx = CallerContext(
        user_id="demo-user", tenant_id="tenant-demo",
        scopes=frozenset({"amp:read", "amp:migrate"}),
        auth_mechanism="api_key",
    )
    client = IntegrationClient(ctx)

    print("== tools an agent can discover ==")
    for tool in client.list_tools():
        print(f"  {tool['name']} v{tool['version']}: {tool['description']}")

    print("\n== analyze schema ==")
    print(client.analyze_schema("orders").to_dict())

    print("\n== transform tables (batch, one bad table) ==")
    print(client.transform_batch("orders", ["customers", "nope", "orders"]).to_dict())

    print("\n== dry-run migration ==")
    print(client.dry_run_migration("orders").to_dict())

    print("\n== validate migrated rows ==")
    print(client.validate_migrated(3000, 3000).to_dict())

    print("\n== model suggestion (seeded, reproducible) ==")
    print(client.suggest_mapping("map the orders table", seed=7).to_dict())

    print("\n== diagnostics ==")
    print(client.registry.observer.diagnostics("amp.dry_run_migration"))


if __name__ == "__main__":
    main()
