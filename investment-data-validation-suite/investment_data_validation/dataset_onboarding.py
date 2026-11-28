"""Dataset onboarding for a systematic data-services team.

Covers the Cubist Data Services work: onboarding novel datasets from many
sources, profiling them, reshaping and aggregating them into features,
defining automated qualitative data alerts, and summarising preliminary
analysis for investment teams. Standard library only; all data is seeded
and synthetic (see data.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import Finding, ValidationReport

# Onboarding lifecycle. A dataset moves one step at a time; skipping a
# step (e.g. straight from PROPOSED to LIVE) is an error, so nothing
# reaches production without being profiled and validated first.
STATUSES = ("PROPOSED", "PROFILED", "VALIDATED", "LIVE")
_ALLOWED_NEXT = {
    "PROPOSED": ("PROFILED",),
    "PROFILED": ("VALIDATED",),
    "VALIDATED": ("LIVE",),
    "LIVE": (),
}


@dataclass
class ColumnProfile:
    """Inferred shape of one column in an onboarded dataset."""

    name: str
    inferred_type: str  # int, float, str, date, bool, or unknown
    non_null: int
    distinct: int

    @property
    def completeness(self) -> float:
        return self.non_null / self.total if self.total else 0.0

    total: int = 0


@dataclass
class DatasetProfile:
    """Profile of one onboarded dataset: shape, freshness, coverage."""

    name: str
    source: str
    rows: int
    columns: list[ColumnProfile]
    latest_as_of: date | None
    earliest_as_of: date | None
    owner_team: str = ""
    status: str = "PROPOSED"

    @property
    def completeness(self) -> float:
        if not self.columns:
            return 0.0
        return min(c.completeness for c in self.columns)


@dataclass
class DatasetFeature:
    """One per-security feature built by reshaping trade and master data."""

    security_id: str
    trade_count: int
    total_quantity: float
    vwap: float | None
    min_price: float | None
    max_price: float | None
    last_trade_date: str | None
    notional: float | None  # total traded notional (quantity x price)
    price_range_pct: float | None  # (max - min) / vwap, a spread feature


@dataclass
class Alert:
    """One automated qualitative data alert."""

    rule: str
    dataset: str
    severity: str  # FAIL or WARNING
    message: str


def _infer_type(values: list) -> str:
    seen = {type(v).__name__ for v in values if v is not None}
    if not seen:
        return "unknown"
    if seen <= {"bool"}:
        return "bool"
    if seen <= {"int"}:
        return "int"
    if seen <= {"int", "float"}:
        return "float"
    if seen <= {"str"}:
        for v in values:
            if isinstance(v, str):
                try:
                    date.fromisoformat(v)
                except ValueError:
                    return "str"
        return "date"
    return "str"


def _parse_date(value) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def profile_dataset(
    name: str,
    source: str,
    rows: list[dict],
    owner_team: str = "",
) -> DatasetProfile:
    """Profile a novel dataset: infer each column's type, completeness and
    distinct counts, and find the latest as-of date in any date column."""
    columns: list[ColumnProfile] = []
    latest: date | None = None
    earliest: date | None = None
    if rows:
        for key in rows[0]:
            values = [r.get(key) for r in rows]
            non_null = [v for v in values if v is not None]
            distinct = len({repr(v) for v in non_null})
            col = ColumnProfile(
                name=key,
                inferred_type=_infer_type(non_null),
                non_null=len(non_null),
                distinct=distinct,
                total=len(rows),
            )
            columns.append(col)
            for v in non_null:
                parsed = _parse_date(v)
                if parsed is not None:
                    if latest is None or parsed > latest:
                        latest = parsed
                    if earliest is None or parsed < earliest:
                        earliest = parsed
    return DatasetProfile(
        name=name,
        source=source,
        rows=len(rows),
        columns=columns,
        latest_as_of=latest,
        earliest_as_of=earliest,
        owner_team=owner_team,
    )


def register_dataset(
    registry: dict[str, DatasetProfile],
    profile: DatasetProfile,
    owner_team: str,
    status: str = "PROFILED",
) -> DatasetProfile:
    """Add a dataset to the onboarding registry, or advance its status.

    A new dataset starts at PROFILED once its profile exists; later calls
    move it one step forward. An illegal jump raises ValueError instead of
    silently promoting unvalidated data.
    """
    existing = registry.get(profile.name)
    if existing is None:
        if status != "PROFILED":
            raise ValueError(
                f"{profile.name}: a new dataset must start at PROFILED, "
                f"not {status}"
            )
        profile.owner_team = owner_team
        profile.status = "PROFILED"
        registry[profile.name] = profile
        return profile
    if status not in _ALLOWED_NEXT[existing.status]:
        raise ValueError(
            f"{profile.name}: cannot move from {existing.status} to "
            f"{status}; next allowed: {_ALLOWED_NEXT[existing.status]}"
        )
    existing.status = status
    return existing


def build_security_features(
    securities: list[dict], trades: list[dict]
) -> list[DatasetFeature]:
    """Reshape trade and security-master rows into per-security features.

    VWAP is quantity-weighted price; notional is total traded value;
    price_range_pct is the traded price spread relative to VWAP.
    Securities with no trades keep trade_count 0 and null price features
    instead of invented values.
    """
    by_security: dict[str, list[dict]] = {}
    for t in trades:
        by_security.setdefault(str(t.get("security_id")), []).append(t)
    features: list[DatasetFeature] = []
    for s in securities:
        sid = str(s["security_id"])
        rows = by_security.get(sid, [])
        if not rows:
            features.append(
                DatasetFeature(sid, 0, 0.0, None, None, None, None, None,
                               None)
            )
            continue
        quantities = [float(r["quantity"]) for r in rows]
        prices = [float(r["price"]) for r in rows]
        total_qty = sum(quantities)
        notional = sum(q * p for q, p in zip(quantities, prices))
        vwap = notional / total_qty if total_qty else None
        price_range_pct = (
            round((max(prices) - min(prices)) / vwap, 4)
            if vwap else None
        )
        features.append(
            DatasetFeature(
                security_id=sid,
                trade_count=len(rows),
                total_quantity=total_qty,
                vwap=round(vwap, 4) if vwap is not None else None,
                min_price=min(prices),
                max_price=max(prices),
                last_trade_date=max(str(r["trade_date"]) for r in rows),
                notional=round(notional, 2),
                price_range_pct=price_range_pct,
            )
        )
    return features


def validate_novel_dataset(
    profile: DatasetProfile,
    rows: list[dict],
    required_columns: list[str],
    key_column: str | None = None,
    known_ids: set[str] | None = None,
    as_of: date | None = None,
) -> ValidationReport:
    """Validate an onboarded dataset the way the other validators do:
    required columns present, no duplicate keys, no orphan references,
    numeric ranges sane, and the feed fresh as of the given date."""
    findings: list[Finding] = []
    checks = passed = failed = 0

    def check(ok: bool, check_name: str, record_id: str, message: str,
              severity: str = "FAIL") -> None:
        nonlocal checks, passed, failed
        checks += 1
        if ok:
            passed += 1
        elif severity == "WARNING":
            findings.append(Finding(check_name, profile.name, record_id,
                                    severity, message))
        else:
            failed += 1
            findings.append(Finding(check_name, profile.name, record_id,
                                    severity, message))

    present = {c.name for c in profile.columns}
    for col in required_columns:
        check(col in present, "required_columns", profile.name,
              f"Required column {col!r} missing from {profile.name}")
    seen_keys: set[str] = set()
    for i, row in enumerate(rows):
        rid = str(row.get(key_column) or f"row-{i}")
        if key_column:
            key = str(row.get(key_column))
            if key in seen_keys:
                check(False, "unique_key", rid,
                      f"Duplicate {key_column} {key!r}")
            else:
                seen_keys.add(key)
                check(True, "unique_key", rid, "")
        if known_ids is not None and "security_id" in row:
            check(str(row["security_id"]) in known_ids, "known_security",
                  rid, f"security_id {row['security_id']!r} is not in the "
                  "security master")
        for key, value in row.items():
            if key in ("esg_score", "environmental", "social", "governance"):
                ok = value is not None and 0 <= float(value) <= 100
                check(ok, "score_range", rid,
                      f"{key} {value} outside 0-100" if value is not None
                      else f"{key} is missing",
                      severity="WARNING")
            if key == "spot_rate":
                ok = value is not None and float(value) > 0
                check(ok, "positive_rate", rid,
                      f"spot_rate {value} must be positive"
                      if value is not None else "spot_rate is missing",
                      severity="WARNING")
    if as_of is not None:
        check(profile.earliest_as_of is not None
              and profile.earliest_as_of >= as_of, "freshness", profile.name,
              f"Earliest as-of {profile.earliest_as_of} is stale vs {as_of}",
              severity="WARNING")
    return ValidationReport(profile.name, len(rows), checks, passed, failed,
                            findings)


def evaluate_alerts(
    profiles: list[DatasetProfile],
    features: list[DatasetFeature],
    prior_row_counts: dict[str, int],
    as_of: date,
    min_completeness: float = 0.95,
    max_row_drift: float = 0.10,
    max_price_range_pct: float = 0.30,
) -> list[Alert]:
    """Automated qualitative data alerts: stale feeds, incomplete columns,
    row-count drift vs the prior day, and out-of-range derived features.
    A traded price range over 30% of VWAP is anomalous for these
    instruments, so it alerts; the seeded 85-112 price band alone stays
    under it."""
    alerts: list[Alert] = []
    for p in profiles:
        if p.earliest_as_of is None or p.earliest_as_of < as_of:
            alerts.append(Alert(
                "freshness", p.name, "WARNING",
                f"{p.name}: earliest as-of {p.earliest_as_of} is before "
                f"{as_of} — some rows are stale"))
        for c in p.columns:
            if c.completeness < min_completeness:
                alerts.append(Alert(
                    "completeness", p.name, "WARNING",
                    f"{p.name}.{c.name}: {c.completeness:.0%} complete "
                    f"({c.non_null}/{c.total}) — below {min_completeness:.0%}"))
        prior = prior_row_counts.get(p.name)
        if prior and abs(p.rows - prior) / prior > max_row_drift:
            alerts.append(Alert(
                "row_count_drift", p.name, "WARNING",
                f"{p.name}: {p.rows} rows vs {prior} yesterday "
                f"({(p.rows - prior) / prior:+.0%} change)"))
    for f in features:
        if f.vwap is not None and not 50 <= f.vwap <= 150:
            alerts.append(Alert(
                "feature_range", "security_features", "WARNING",
                f"{f.security_id}: VWAP {f.vwap} outside 50-150"))
        if (f.price_range_pct is not None
                and f.price_range_pct > max_price_range_pct):
            alerts.append(Alert(
                "feature_range", "security_features", "WARNING",
                f"{f.security_id}: traded price range "
                f"{f.price_range_pct:.1%} of VWAP exceeds "
                f"{max_price_range_pct:.0%}"))
    return alerts


def investment_team_summary(
    profiles: list[DatasetProfile],
    features: list[DatasetFeature],
    alerts: list[Alert],
) -> dict:
    """Preliminary analysis to share with investment teams: which datasets
    are live, the most-traded securities by notional, and open alerts."""
    traded = [f for f in features if f.trade_count > 0]
    top = sorted(traded, key=lambda f: f.notional or 0, reverse=True)[:3]
    return {
        "datasets": [
            {"name": p.name, "source": p.source, "rows": p.rows,
             "status": p.status, "latest_as_of":
             p.latest_as_of.isoformat() if p.latest_as_of else None}
            for p in profiles
        ],
        "securities_with_trades": len(traded),
        "top_by_notional": [
            {"security_id": f.security_id, "trade_count": f.trade_count,
             "vwap": f.vwap, "notional": f.notional} for f in top
        ],
        "open_alerts": len(alerts),
        "alerts": [
            {"rule": a.rule, "dataset": a.dataset, "severity": a.severity,
             "message": a.message} for a in alerts
        ],
    }
