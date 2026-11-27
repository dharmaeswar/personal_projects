"""End-to-end demo: seed -> DAG -> serve one sample user.

All data is synthetic (seed 42). No cloud services are called.
"""
from __future__ import annotations

import os
from datetime import datetime

from signals.batch import build_batch_signals, build_user_context
from signals.ingest import ingest_batch, retry_quarantined
from signals.orchestration import Orchestrator, Task
from signals.quality import check_events, check_signals
from signals.realtime import merge_signals, realtime_signals
from signals.seed import seed_consents, seed_events
from signals.serve import SignalServer
from signals.store import Store

NOW = datetime(2026, 11, 26, 12, 0, 0)
RUN_ID = "demo-20261126"


def main() -> None:
    store = Store(os.path.join(os.path.dirname(__file__), "data", "store.json"))
    consents = seed_consents()
    context: dict = {"store": store, "consents": consents, "now": NOW,
                     "run_id": RUN_ID, "inputs": {}}

    def t_ingest(ctx):
        raw = seed_events(NOW)
        ctx["inputs"]["ingest"] = str(len(raw))
        accepted, quarantined = ingest_batch(raw, store.event_ids(), now=NOW)
        ctx["accepted"] = accepted
        ctx["quarantined"] = quarantined
        store.add_events(accepted)
        return {"accepted": len(accepted), "quarantined": len(quarantined)}

    def t_validate(ctx):
        problems = check_events(store.events(), NOW)
        assert not problems, problems
        return {"problems": problems}

    def t_batch(ctx):
        profiles, signals = {}, []
        for user_id, consent in consents.items():
            profile = build_user_context(user_id, store.events(), consent, RUN_ID, NOW)
            profiles[user_id] = profile
            store.put_profile(profile)
            signals.extend(build_batch_signals(profile, RUN_ID))
        ctx["batch_signals"] = signals
        return {"profiles": len(profiles), "signals": len(signals)}

    def t_quality(ctx):
        realtime = []
        for user_id, consent in consents.items():
            realtime.extend(realtime_signals(user_id, store.events(), consent, RUN_ID, NOW))
        merged = merge_signals(ctx["batch_signals"], realtime)
        problems = check_signals(merged, store.events())
        assert not problems, problems
        ctx["merged"] = merged
        return {"problems": problems, "merged_signals": len(merged)}

    def t_publish(ctx):
        store.put_signals(ctx["merged"])
        return {"published": len(ctx["merged"])}

    tasks = [
        Task("ingest", t_ingest),
        Task("validate", t_validate, depends_on=("ingest",)),
        Task("batch", t_batch, depends_on=("validate",)),
        Task("quality", t_quality, depends_on=("batch",)),
        Task("publish", t_publish, depends_on=("quality",)),
    ]
    results = Orchestrator().run(RUN_ID, tasks, context)
    for name, result in results.items():
        print(f"{name}: {result}")

    server = SignalServer(store, consents, run_id=RUN_ID, now=NOW)
    served, withheld = server.signals_for_user("user-01")
    print(f"\nServed for user-01 ({len(served)} signals):")
    for signal in served[:6]:
        print(f"  {signal['signal_type']:20s} {signal['value']:25s} "
              f"score={signal['score']:.3f} source={signal['source']}")
    served3, withheld3 = server.signals_for_user("user-03")
    print(f"\nuser-03 (telemetry consent off): {len(served3)} served, "
          f"withheld categories: {withheld3}")
    print(f"\nQuarantined rows: {len(context['quarantined'])} "
          f"(planted bad rows, all caught)")


if __name__ == "__main__":
    main()
