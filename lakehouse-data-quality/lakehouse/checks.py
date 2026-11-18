"""Data-quality checks for lakehouse tables.

Every check returns a :class:`CheckResult` with a name, a pass/fail flag,
and the detail a reviewer needs (how many rows failed, and which ones).
Checks never raise on bad data — a failing check is a result, not an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

MAX_ORDER_DATE = pd.Timestamp("2026-11-30")
MIN_ORDER_DATE = pd.Timestamp("2026-01-01")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    failing_rows: list[int] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - convenience only
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.detail}"


def check_completeness(df: pd.DataFrame, columns: list[str]) -> CheckResult:
    """Fail if any listed column holds nulls; report the null count per column."""
    parts = []
    failing: set[int] = set()
    for col in columns:
        n = int(df[col].isna().sum()) if col in df.columns else len(df)
        if n:
            parts.append(f"{col}: {n} nulls")
            failing.update(df.index[df[col].isna()].tolist())
    if not parts:
        return CheckResult("completeness", True, "no nulls in checked columns")
    return CheckResult(
        "completeness",
        False,
        "; ".join(parts),
        sorted(failing),
    )


def check_uniqueness(df: pd.DataFrame, column: str) -> CheckResult:
    """Fail if ``column`` holds duplicate values; report the extra (later) rows."""
    dup_mask = df.duplicated(subset=[column], keep="first")
    n_dup_rows = int(dup_mask.sum())
    if n_dup_rows == 0:
        return CheckResult(
            f"uniqueness:{column}", True, f"all {len(df)} values of {column} unique"
        )
    n_dup_values = int(df.loc[dup_mask, column].nunique())
    return CheckResult(
        f"uniqueness:{column}",
        False,
        f"{n_dup_values} duplicated {column} values ({n_dup_rows} extra rows)",
        sorted(df.index[dup_mask].tolist()),
    )


def check_ranges(
    df: pd.DataFrame,
    column: str,
    low=None,
    high=None,
) -> CheckResult:
    """Fail if any value in ``column`` falls outside [low, high]."""
    failing: set[int] = set()
    if low is not None:
        failing.update(df.index[df[column] < low].tolist())
    if high is not None:
        failing.update(df.index[df[column] > high].tolist())
    if not failing:
        return CheckResult(f"range:{column}", True, f"all values of {column} in range")
    return CheckResult(
        f"range:{column}",
        False,
        f"{len(failing)} rows outside range for {column}",
        sorted(failing),
    )


def check_referential_integrity(
    df: pd.DataFrame,
    column: str,
    reference: pd.DataFrame,
    reference_column: str,
) -> CheckResult:
    """Fail if any non-null value in ``column`` is missing from the reference table."""
    ref_values = set(reference[reference_column].dropna().unique())
    mask = df[column].notna() & ~df[column].isin(ref_values)
    n = int(mask.sum())
    if n == 0:
        return CheckResult(
            f"fk:{column}->{reference_column}",
            True,
            f"all {column} values found in {reference_column}",
        )
    return CheckResult(
        f"fk:{column}->{reference_column}",
        False,
        f"{n} rows with {column} not in {reference_column}",
        sorted(df.index[mask].tolist()),
    )


def check_totals(df: pd.DataFrame, tolerance: float = 0.01) -> CheckResult:
    """Fail if total_amount differs from quantity * unit_price by more than tolerance."""
    expected = (df["quantity"] * df["unit_price"]).round(2)
    diff = (df["total_amount"] - expected).abs()
    mask = diff > tolerance
    n = int(mask.sum())
    if n == 0:
        return CheckResult(
            "totals", True, "total_amount equals quantity * unit_price on every row"
        )
    return CheckResult(
        "totals",
        False,
        f"{n} rows where total_amount != quantity * unit_price",
        sorted(df.index[mask].tolist()),
    )


def check_reconciliation(
    silver_orders: pd.DataFrame,
    products: pd.DataFrame,
    gold: pd.DataFrame,
    tolerance: float = 0.01,
) -> CheckResult:
    """Fail if gold daily revenue does not match silver revenue grouped the same way."""
    merged = silver_orders.merge(
        products[["product_id", "category"]], on="product_id", how="left"
    )
    merged["order_day"] = merged["order_date"].dt.normalize()
    expected = (
        merged.groupby(["order_day", "category", "region"], as_index=False)
        .agg(order_count=("order_id", "count"), total_revenue=("total_amount", "sum"))
        .rename(columns={"order_day": "order_date"})
    )
    expected["total_revenue"] = expected["total_revenue"].round(2)
    got = gold.copy()
    got["total_revenue"] = got["total_revenue"].round(2)
    merged_check = expected.merge(
        got,
        on=["order_date", "category", "region"],
        how="outer",
        suffixes=("_expected", "_got"),
        indicator=True,
    )
    problems = []
    only_expected = merged_check[merged_check["_merge"] == "left_only"]
    only_got = merged_check[merged_check["_merge"] == "right_only"]
    if len(only_expected):
        problems.append(f"{len(only_expected)} gold groups missing")
    if len(only_got):
        problems.append(f"{len(only_got)} unexpected gold groups")
    both = merged_check[merged_check["_merge"] == "both"]
    if len(both):
        count_diff = (both["order_count_expected"] != both["order_count_got"]).sum()
        rev_diff = (
            both["total_revenue_expected"] - both["total_revenue_got"]
        ).abs() > tolerance
        if count_diff:
            problems.append(f"{int(count_diff)} groups with wrong order_count")
        if int(rev_diff.sum()):
            problems.append(f"{int(rev_diff.sum())} groups with wrong total_revenue")
    if not problems:
        return CheckResult(
            "reconciliation",
            True,
            f"gold matches silver on all {len(expected)} daily groups",
        )
    return CheckResult("reconciliation", False, "; ".join(problems))


def run_all_checks(
    bronze_orders: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
) -> list[CheckResult]:
    """Run the full bronze check suite on the orders table."""
    return [
        check_completeness(
            bronze_orders, ["order_id", "customer_id", "product_id", "order_date"]
        ),
        check_uniqueness(bronze_orders, "order_id"),
        check_ranges(bronze_orders, "quantity", low=1),
        check_ranges(bronze_orders, "unit_price", low=0),
        check_ranges(
            bronze_orders, "order_date", low=MIN_ORDER_DATE, high=MAX_ORDER_DATE
        ),
        check_referential_integrity(
            bronze_orders, "customer_id", customers, "customer_id"
        ),
        check_referential_integrity(
            bronze_orders, "product_id", products, "product_id"
        ),
        check_totals(bronze_orders),
    ]
