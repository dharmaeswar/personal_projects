"""Research Event Replay Framework.

A research-technology toolkit for quant researchers: ingest raw exchange
tick data, store it in a columnar Parquet layout, replay it deterministically
through a simulation loop, slice and backtest it from Python, and schedule
the heavy jobs on a Slurm-style cluster queue.

All market data is synthetic and seeded. No real exchange data, no real
trading, and no claim about any real firm or strategy is involved.
"""

__all__ = ["ingest", "store", "replay", "backtest", "scheduler"]
__version__ = "1.0.0"
