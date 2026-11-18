"""Allow ``python -m vol_surface_checker <surface.csv>``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
