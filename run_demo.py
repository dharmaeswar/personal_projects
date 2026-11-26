"""End-to-end demo: generate synthetic safety data and print the briefing."""

from safetyint.data import generate_events, monthly_counts
from safetyint.report import build_briefing, render_briefing_text

if __name__ == "__main__":
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    print(f"Generated {len(events)} synthetic safety events over "
          f"{len(exposure)} months.")
    print(render_briefing_text(build_briefing(counts, exposure)))
