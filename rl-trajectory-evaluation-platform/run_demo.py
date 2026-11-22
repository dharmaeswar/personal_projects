"""Seed a demo store and print the platform dashboard as JSON."""

import json

from rl_platform import demo_store, observability


def main():
    store = demo_store()
    env_id = next(iter(store["environments"]))
    print(json.dumps(observability.dashboard(store, {env_id: 10}), indent=2))


if __name__ == "__main__":
    main()
