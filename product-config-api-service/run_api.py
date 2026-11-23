"""Run the local product-config API server."""

import os

os.environ.setdefault("CONFIG_STORE_PATH", os.path.join(os.path.dirname(__file__), "configs.json"))

from product_config.api import main

if __name__ == "__main__":
    main()
