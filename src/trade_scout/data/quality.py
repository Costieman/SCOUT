"""Deterministic quality checks for canonical daily market data."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from math import isfinite

from trade_scout.data.contracts import DailyBar, QualityStatus


class QualityRule(StrEnum):
    """Stable identifiers for initial daily-bar quality rules."""

    DUPLICATE_INSTRUMENT_DATE = "duplicate_instrument_date"
    NON_FINITE_PRICE = "non_finite_price"
    NEGATIVE_PRICE = "negative_price"
    NEGATIVE_VOLUME = "negative_volume"
    HIGH_BELOW_LOW = "high_below_low"
    OPEN_OUTSIDE_RANGE = "open_outside_range"
    CLOSE_OUTSIDE_RANGE = "close_outside_range"
    INVALID_SPLIT_FACTOR = "invalid_split_factor"
    NEGATIVE_DIVIDEND = "negative_dividend"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """One machine-readable quality violation; source data are never repaired here."""

    rule: QualityRule
    status: QualityStatus
    instrument_id: str
    trade_date: str
    message: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Batch-level quality result with all detected issues retained."""

    status: QualityStatus
    record_count: int
    issues: tuple[QualityIssue, ...]


_STATUS_RANK = {
    QualityStatus.PASS: 0,
    QualityStatus.WARN: 1,
    QualityStatus.QUARANTINE: 2,
    QualityStatus.REJECT: 3,
}


def _worst_status(issues: Iterable[QualityIssue]) -> QualityStatus:
    status = QualityStatus.PASS
    for issue in issues:
        if _STATUS_RANK[issue.status] > _STATUS_RANK[status]:
            status = issue.status
    return status


def validate_daily_bars(bars: Iterable[DailyBar]) -> QualityReport:
    """Validate daily bars without mutating, coercing, or filling source observations."""

    materialized = tuple(bars)
    issues: list[QualityIssue] = []
    seen: set[tuple[str, date]] = set()

    for bar in materialized:
        identity = (str(bar.instrument_id), bar.trade_date)
        if identity in seen:
            issues.append(
                _issue(
                    bar,
                    QualityRule.DUPLICATE_INSTRUMENT_DATE,
                    QualityStatus.REJECT,
                    "duplicate canonical instrument/date record",
                )
            )
        else:
            seen.add(identity)

        raw_prices = (bar.open_raw, bar.high_raw, bar.low_raw, bar.close_raw)
        if not all(isfinite(value) for value in raw_prices):
            issues.append(
                _issue(
                    bar,
                    QualityRule.NON_FINITE_PRICE,
                    QualityStatus.REJECT,
                    "raw OHLC contains a non-finite value",
                )
            )
            continue

        if any(value < 0 for value in raw_prices):
            issues.append(
                _issue(
                    bar,
                    QualityRule.NEGATIVE_PRICE,
                    QualityStatus.REJECT,
                    "raw OHLC contains a negative price",
                )
            )

        if bar.volume_raw < 0:
            issues.append(
                _issue(
                    bar,
                    QualityRule.NEGATIVE_VOLUME,
                    QualityStatus.REJECT,
                    "reported volume is negative",
                )
            )

        if bar.high_raw < bar.low_raw:
            issues.append(
                _issue(
                    bar,
                    QualityRule.HIGH_BELOW_LOW,
                    QualityStatus.REJECT,
                    "reported high is below reported low",
                )
            )
        else:
            if not bar.low_raw <= bar.open_raw <= bar.high_raw:
                issues.append(
                    _issue(
                        bar,
                        QualityRule.OPEN_OUTSIDE_RANGE,
                        QualityStatus.QUARANTINE,
                        "reported open is outside the reported high-low interval",
                    )
                )
            if not bar.low_raw <= bar.close_raw <= bar.high_raw:
                issues.append(
                    _issue(
                        bar,
                        QualityRule.CLOSE_OUTSIDE_RANGE,
                        QualityStatus.QUARANTINE,
                        "reported close is outside the reported high-low interval",
                    )
                )

        if not isfinite(bar.split_factor) or bar.split_factor <= 0:
            issues.append(
                _issue(
                    bar,
                    QualityRule.INVALID_SPLIT_FACTOR,
                    QualityStatus.QUARANTINE,
                    "split factor must be finite and positive",
                )
            )

        if not isfinite(bar.dividend_cash) or bar.dividend_cash < 0:
            issues.append(
                _issue(
                    bar,
                    QualityRule.NEGATIVE_DIVIDEND,
                    QualityStatus.QUARANTINE,
                    "cash dividend must be finite and non-negative",
                )
            )

    frozen_issues = tuple(issues)
    return QualityReport(
        status=_worst_status(frozen_issues),
        record_count=len(materialized),
        issues=frozen_issues,
    )


def _issue(
    bar: DailyBar,
    rule: QualityRule,
    status: QualityStatus,
    message: str,
) -> QualityIssue:
    return QualityIssue(
        rule=rule,
        status=status,
        instrument_id=str(bar.instrument_id),
        trade_date=bar.trade_date.isoformat(),
        message=message,
    )
