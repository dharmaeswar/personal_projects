"""Restaurant Order Streaming Pipeline — demo entry point.

Seeds synthetic order events, runs the full pipeline, and prints the run
summary (batches, clean/quarantined/late counts, partitions written, and
the governance report). Nothing here touches a real restaurant system.
"""
from order_stream.pipeline import run_pipeline

if __name__ == "__main__":
    state, report = run_pipeline()
    print(f"batches: {state.batches}")
    print(f"produced: {state.produced}  clean: {state.clean}  "
          f"quarantined: {state.quarantined}  late: {state.late}")
    print(f"partitions written: {state.partitions_written}")
    print(f"errors: {state.errors}")
    print(f"governance: {report}")
