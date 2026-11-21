"""Allow `python -m product_analytics` to run the pipeline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_pipeline  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_pipeline.main())
