"""Demo: build a Homepage feed from three product teams.

- approvals: fast, on budget.
- receipts: slow this run (900ms vs the 250ms budget), so the feed serves its
  cached tasks flagged stale instead of stalling.
- setup: fails outright, and there is no cache yet, so it contributes nothing
  and the feed carries a notice.

Then an experiment readout shows whether the new ranking variant improved
task completion.
"""

from datetime import datetime, timedelta, timezone

from taskfeed import (
    FeedBuilder,
    assign_variant,
    detail_view,
    readout,
)
from taskfeed.models import Task

NOW = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)


def t(source, ext, title, kind, priority, days_old=1, due_in=None, relevance=0.5, **payload):
    return Task(
        source=source, external_id=ext, title=title, kind=kind, priority=priority,
        created_at=NOW - timedelta(days=days_old),
        due_at=NOW + timedelta(days=due_in) if due_in is not None else None,
        relevance=relevance, payload=payload,
    )


def main() -> None:
    builder = FeedBuilder(budget_ms=250.0)
    # Seed the receipts cache with yesterday's tasks so degradation has data.
    builder.cache.store("receipts", [t(
        "receipts", "r1", "Match receipt: Delta $412.10", "receipt", 2,
        due_in=1, relevance=0.6, merchant="Delta", amount="$412.10",
        matched_expense="Flight — NYC client visit", receipt_date="2026-11-27")])

    feed = builder.build({
        "approvals": lambda: ([
            t("approvals", "a1", "Approve $1,200 vendor invoice", "approval", 5,
              due_in=0, relevance=0.9, requester="Ana Patel", amount="$1,200",
              vendor="Acme Supplies", policy_checks="pass"),
            t("approvals", "a2", "Approve travel: SF onsite", "approval", 3,
              due_in=3, relevance=0.5, requester="Ben Cho", amount="$860",
              vendor="United", policy_checks="pass"),
        ], 80.0),
        "receipts": lambda: ([t(
            "receipts", "r1", "Match receipt: Delta $412.10", "receipt", 2,
            due_in=1, relevance=0.6)], 900.0),  # over budget -> stale cache
        "setup": lambda: (_ for _ in ()).throw(RuntimeError("connection reset")),
    }, user="dharma", now=NOW)

    print("Homepage feed — ranked, actionable tasks")
    print("=" * 60)
    for task in feed.tasks:
        stale = " [STALE]" if task.stale else ""
        print(f"[{feed.scores[task.key]:7.1f}] {task.title} ({task.source}){stale}")
    print(f"\nSources: {', '.join(f'{s.source}={s.status}' for s in feed.sources)}")
    for notice in feed.notices:
        print(f"Notice: {notice}")

    top = feed.top(1)[0]
    view = detail_view(top)
    print(f"\nDetail view — {view.title}")
    for label, value in view.fields:
        print(f"  {label}: {value}")
    print(f"  Actions: {', '.join(view.actions)}")

    print(f"\nExperiment ranking-v2 for dharma: {assign_variant('dharma', 'ranking-v2')}")
    result = readout("ranking-v2", control_success=412, control_n=1000,
                     treatment_success=471, treatment_n=1000)
    print(f"Readout: control {result.rate_control:.1%}, treatment {result.rate_treatment:.1%}, "
          f"lift {result.lift:+.1f} pts, p={result.p_value} — {result.note}")


if __name__ == "__main__":
    main()
