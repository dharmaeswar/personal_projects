"""Market-regulation analytics toolkit: order/trade/position warehouse
analysis, trade-pattern detection and regulatory reporting."""

from .data import WarehouseConfig, build_positions, build_warehouse, generate_orders_trades, load_table
from .patterns import (
    detect_marking_the_close,
    detect_position_concentration,
    detect_spoofing,
    detect_wash_trades,
    run_all_detectors,
)
from .report import findings_summary, write_report
from .stats import account_volume_share, add_zscores, daily_volume, flag_outlier_days, price_move_stats

__all__ = [
    "WarehouseConfig",
    "build_positions",
    "build_warehouse",
    "generate_orders_trades",
    "load_table",
    "detect_marking_the_close",
    "detect_position_concentration",
    "detect_spoofing",
    "detect_wash_trades",
    "run_all_detectors",
    "findings_summary",
    "write_report",
    "account_volume_share",
    "add_zscores",
    "daily_volume",
    "flag_outlier_days",
    "price_move_stats",
]
