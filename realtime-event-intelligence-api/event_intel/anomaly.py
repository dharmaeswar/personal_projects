"""AI/ML-enabled anomaly detection over streaming telemetry.

The Zscaler Data & APIs role asks for anomaly detection and signal
correlation over streaming telemetry using statistical, rules-based, or
ML techniques. This module implements the statistical and rules-based
half on windowed telemetry counts (events per window per source), plus
cross-source signal correlation:

- Z-score detector: flags windows whose count is far from the rolling
  mean, in standard deviations.
- MAD detector: the same idea with median / median absolute deviation,
  robust when the baseline itself contains spikes.
- Rules detector: plain thresholds — an absolute count ceiling and a
  rate-of-change rule (count more than doubled vs the previous window).
- Correlation: anomalies from different sources in the same window are
  grouped into one correlated signal, the way an analyst would treat
  "three sources spiked together" as one incident, not three.

All inputs are synthetic counts supplied by the caller; nothing here
reads real Zscaler telemetry. The detectors are deliberately simple and
documented as such — they demonstrate the technique and the interfaces,
not a production ML model.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class Anomaly:
    source: str
    window_start: float
    detector: str
    value: float
    baseline: float
    severity: str  # "warning" or "critical"
    evidence: str


@dataclass
class DetectorResult:
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def critical(self) -> list[Anomaly]:
        return [a for a in self.anomalies if a.severity == "critical"]


def _severity(score: float, critical_at: float) -> str:
    return "critical" if score >= critical_at else "warning"


def zscore_detect(source: str, counts: list[float], *,
                  window: int = 10, z_threshold: float = 3.0,
                  critical_z: float = 5.0) -> DetectorResult:
    """Flag windows whose count is z standard deviations from the mean.

    `counts` is a per-window series (oldest first). Each value is scored
    against the rolling mean/std of the previous `window` values, so a
    spike is judged against recent history, not the whole series.
    """
    result = DetectorResult()
    if window < 2:
        raise ValueError("window must be >= 2")
    for i, value in enumerate(counts):
        history = counts[max(0, i - window):i]
        if len(history) < 5:
            # Too little history: a z-score from 2 points is noise, not
            # a signal. Wait until the rolling baseline is stable.
            continue
        mean = statistics.fmean(history)
        std = statistics.pstdev(history)
        if std == 0:
            continue
        z = (value - mean) / std
        if abs(z) >= z_threshold:
            result.anomalies.append(Anomaly(
                source=source, window_start=float(i), detector="zscore",
                value=value, baseline=round(mean, 2),
                severity=_severity(abs(z), critical_z),
                evidence=f"z={z:.2f} vs rolling mean {mean:.1f} "
                         f"(std {std:.1f}, n={len(history)})",
            ))
    return result


def mad_detect(source: str, counts: list[float], *,
               window: int = 10, threshold: float = 3.5,
               critical_at: float = 6.0) -> DetectorResult:
    """Median/MAD detector: robust to spikes already in the baseline."""
    result = DetectorResult()
    if window < 2:
        raise ValueError("window must be >= 2")
    for i, value in enumerate(counts):
        history = counts[max(0, i - window):i]
        if len(history) < 5:
            # Too little history: a MAD score from 2 points is noise.
            continue
        median = statistics.median(history)
        mad = statistics.median([abs(v - median) for v in history])
        if mad == 0:
            continue
        score = abs(value - median) / (1.4826 * mad)
        if score >= threshold:
            result.anomalies.append(Anomaly(
                source=source, window_start=float(i), detector="mad",
                value=value, baseline=median,
                severity=_severity(score, critical_at),
                evidence=f"modified z={score:.2f} vs median {median:.1f} "
                         f"(MAD {mad:.1f}, n={len(history)})",
            ))
    return result


def rule_detect(source: str, counts: list[float], *,
                max_count: float, max_growth: float = 2.0) -> DetectorResult:
    """Rules-based detector: absolute ceiling + rate-of-change rule."""
    result = DetectorResult()
    previous = None
    for i, value in enumerate(counts):
        if value > max_count:
            result.anomalies.append(Anomaly(
                source=source, window_start=float(i), detector="rule-ceiling",
                value=value, baseline=max_count, severity="critical",
                evidence=f"count {value} exceeds ceiling {max_count}",
            ))
        elif previous is not None and previous > 0 \
                and value / previous >= max_growth:
            result.anomalies.append(Anomaly(
                source=source, window_start=float(i),
                detector="rule-growth", value=value, baseline=previous,
                severity="warning",
                evidence=f"count grew {value / previous:.1f}x "
                         f"vs previous window ({previous})",
            ))
        previous = value
    return result


def correlate(results: list[DetectorResult]) -> list[dict]:
    """Group anomalies from different sources in the same window.

    Returns one correlated signal per (window, detector-family) group
    with two or more sources — the signal an on-call engineer would
    treat as a single incident.
    """
    groups: dict[tuple[float, str], list[Anomaly]] = {}
    for result in results:
        for anomaly in result.anomalies:
            key = (anomaly.window_start, anomaly.detector)
            groups.setdefault(key, []).append(anomaly)
    signals = []
    for (window_start, detector), anomalies in sorted(groups.items()):
        sources = sorted({a.source for a in anomalies})
        if len(sources) < 2:
            continue
        signals.append({
            "window_start": window_start,
            "detector": detector,
            "sources": sources,
            "anomaly_count": len(anomalies),
            "max_severity": "critical" if any(
                a.severity == "critical" for a in anomalies) else "warning",
            "evidence": "; ".join(a.evidence for a in anomalies),
        })
    return signals
