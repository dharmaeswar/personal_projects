"""Demo run: build a small warehouse and print the findings summary."""

from trade_reg_analytics.data import WarehouseConfig, build_warehouse, load_table
from trade_reg_analytics.patterns import run_all_detectors
from trade_reg_analytics.report import findings_summary, write_report
from trade_reg_analytics.stats import daily_volume

if __name__ == "__main__":
    counts = build_warehouse("warehouse.db", WarehouseConfig(seed=42, days=20))
    print("Warehouse:", counts)
    orders = load_table("warehouse.db", "orders")
    trades = load_table("warehouse.db", "trades")
    positions = load_table("warehouse.db", "positions")
    findings = run_all_detectors(orders, trades, positions)
    print(findings_summary(findings))
    print(write_report(findings, daily_volume(trades), "report"))
