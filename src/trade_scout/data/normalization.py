"""Provider-neutral normalization into canonical Trade Scout daily-bar contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentRecord,
    QualityStatus,
    SymbolHistoryRecord,
)
from trade_scout.data.instrument_master import resolve_provider_identity, symbol_as_of
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.quality import QualityIssue, validate_daily_bars


class NormalizationRule(StrEnum):
    """Stable identifiers for conditions that prevent canonical daily-bar normalization."""

    UNRESOLVED_INSTRUMENT = "unresolved_instrument"
    UNRESOLVED_SYMBOL_HISTORY = "unresolved_symbol_history"
    MISSING_SPLIT_FACTOR = "missing_split_factor"
    MISSING_DIVIDEND_CASH = "missing_dividend_cash"
    PARTIAL_ADJUSTED_OHLC = "partial_adjusted_ohlc"


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    """Provider record that cannot be promoted into a canonical daily-bar observation."""

    rule: NormalizationRule
    status: QualityStatus
    provider_id: str
    provider_instrument_id: str
    symbol: str
    trade_date: str
    message: str


@dataclass(frozen=True, slots=True)
class DailyBarNormalizationResult:
    """Canonicalized bars plus unresolved/invalid records retained as explicit issues."""

    bars: tuple[DailyBar, ...]
    normalization_issues: tuple[NormalizationIssue, ...]
    quality_issues: tuple[QualityIssue, ...]
    status: QualityStatus


def normalize_provider_daily_bars(
    provider_bars: Iterable[ProviderDailyBar],
    *,
    instruments: Iterable[InstrumentRecord],
    dataset_version: DatasetVersion,
) -> DailyBarNormalizationResult:
    """Normalize provider bars without ticker matching, adjustment guessing, or silent repair."""

    instrument_records = tuple(instruments)
    canonical: list[DailyBar] = []
    normalization_issues: list[NormalizationIssue] = []

    for provider_bar in provider_bars:
        instrument_id = resolve_provider_identity(
            instrument_records,
            provider_id=provider_bar.provider_id,
            provider_instrument_id=provider_bar.provider_instrument_id,
        )
        if instrument_id is None:
            normalization_issues.append(
                _normalization_issue(
                    provider_bar,
                    rule=NormalizationRule.UNRESOLVED_INSTRUMENT,
                    status=QualityStatus.QUARANTINE,
                    message="provider identity is not linked to a canonical instrument",
                )
            )
            continue

        if provider_bar.split_factor is None:
            normalization_issues.append(
                _normalization_issue(
                    provider_bar,
                    rule=NormalizationRule.MISSING_SPLIT_FACTOR,
                    status=QualityStatus.QUARANTINE,
                    message="split factor is absent; normalization will not assume a unit factor",
                )
            )
            continue

        if provider_bar.dividend_cash is None:
            normalization_issues.append(
                _normalization_issue(
                    provider_bar,
                    rule=NormalizationRule.MISSING_DIVIDEND_CASH,
                    status=QualityStatus.QUARANTINE,
                    message="cash-dividend field is absent; normalization will not assume zero",
                )
            )
            continue

        adjusted = (
            provider_bar.adjusted_open,
            provider_bar.adjusted_high,
            provider_bar.adjusted_low,
            provider_bar.adjusted_close,
        )
        if any(value is None for value in adjusted) and any(
            value is not None for value in adjusted
        ):
            normalization_issues.append(
                _normalization_issue(
                    provider_bar,
                    rule=NormalizationRule.PARTIAL_ADJUSTED_OHLC,
                    status=QualityStatus.QUARANTINE,
                    message="adjusted OHLC must be either complete or entirely unavailable",
                )
            )
            continue

        canonical.append(
            DailyBar(
                instrument_id=instrument_id,
                trade_date=provider_bar.trade_date,
                open_raw=provider_bar.open,
                high_raw=provider_bar.high,
                low_raw=provider_bar.low,
                close_raw=provider_bar.close,
                volume_raw=provider_bar.volume,
                split_factor=provider_bar.split_factor,
                dividend_cash=provider_bar.dividend_cash,
                open_split_adjusted=provider_bar.adjusted_open,
                high_split_adjusted=provider_bar.adjusted_high,
                low_split_adjusted=provider_bar.adjusted_low,
                close_split_adjusted=provider_bar.adjusted_close,
                provider_id=provider_bar.provider_id,
                dataset_version=dataset_version,
                quality_status=QualityStatus.PASS,
            )
        )

    quality_report = validate_daily_bars(canonical)
    quality_by_key = _quality_status_by_key(quality_report.issues)
    annotated = tuple(
        replace(
            bar,
            quality_status=quality_by_key.get(
                (str(bar.instrument_id), bar.trade_date.isoformat()),
                QualityStatus.PASS,
            ),
        )
        for bar in canonical
    )
    frozen_normalization_issues = tuple(normalization_issues)
    overall_status = _worst_status(
        [issue.status for issue in frozen_normalization_issues]
        + [issue.status for issue in quality_report.issues]
    )

    return DailyBarNormalizationResult(
        bars=tuple(
            sorted(
                annotated,
                key=lambda bar: (str(bar.instrument_id), bar.trade_date, bar.provider_id),
            )
        ),
        normalization_issues=frozen_normalization_issues,
        quality_issues=quality_report.issues,
        status=overall_status,
    )


def normalize_provider_daily_bars_identity_aware(
    provider_bars: Iterable[ProviderDailyBar],
    *,
    instruments: Iterable[InstrumentRecord],
    symbol_history: Iterable[SymbolHistoryRecord],
    dataset_version: DatasetVersion,
) -> DailyBarNormalizationResult:
    """Normalize only bars whose permanent identity also has dated symbol-history coverage.

    Provider ``symbol`` remains retrieval/provenance metadata. It is deliberately not compared with
    the canonical historical symbol effective on the bar date because some providers expose a
    continuity series through a current query ticker. The canonical bar is keyed by permanent
    ``instrument_id``; historical display symbols are resolved separately through ``symbol_history``.
    """

    instrument_records = tuple(instruments)
    history_records = tuple(symbol_history)
    eligible_bars: list[ProviderDailyBar] = []
    identity_issues: list[NormalizationIssue] = []

    for provider_bar in provider_bars:
        instrument_id = resolve_provider_identity(
            instrument_records,
            provider_id=provider_bar.provider_id,
            provider_instrument_id=provider_bar.provider_instrument_id,
        )
        if instrument_id is None:
            # Preserve the existing unresolved-instrument classification in the common normalizer.
            eligible_bars.append(provider_bar)
            continue

        historical_symbol = symbol_as_of(
            history_records,
            instrument_id=instrument_id,
            as_of=provider_bar.trade_date,
        )
        if historical_symbol is None:
            identity_issues.append(
                _normalization_issue(
                    provider_bar,
                    rule=NormalizationRule.UNRESOLVED_SYMBOL_HISTORY,
                    status=QualityStatus.QUARANTINE,
                    message=(
                        "canonical instrument is resolved but no dated symbol assignment covers "
                        "this trade date"
                    ),
                )
            )
            continue
        eligible_bars.append(provider_bar)

    normalized = normalize_provider_daily_bars(
        eligible_bars,
        instruments=instrument_records,
        dataset_version=dataset_version,
    )
    all_normalization_issues = tuple(identity_issues) + normalized.normalization_issues
    status = _worst_status(
        [issue.status for issue in all_normalization_issues]
        + [issue.status for issue in normalized.quality_issues]
    )
    return DailyBarNormalizationResult(
        bars=normalized.bars,
        normalization_issues=all_normalization_issues,
        quality_issues=normalized.quality_issues,
        status=status,
    )


def _normalization_issue(
    bar: ProviderDailyBar,
    *,
    rule: NormalizationRule,
    status: QualityStatus,
    message: str,
) -> NormalizationIssue:
    return NormalizationIssue(
        rule=rule,
        status=status,
        provider_id=bar.provider_id,
        provider_instrument_id=bar.provider_instrument_id,
        symbol=bar.symbol,
        trade_date=bar.trade_date.isoformat(),
        message=message,
    )


def _quality_status_by_key(
    issues: Iterable[QualityIssue],
) -> dict[tuple[str, str], QualityStatus]:
    result: dict[tuple[str, str], QualityStatus] = {}
    for issue in issues:
        key = (issue.instrument_id, issue.trade_date)
        current = result.get(key, QualityStatus.PASS)
        result[key] = _worse_status(current, issue.status)
    return result


def _worst_status(statuses: Iterable[QualityStatus]) -> QualityStatus:
    result = QualityStatus.PASS
    for status in statuses:
        result = _worse_status(result, status)
    return result


def _worse_status(first: QualityStatus, second: QualityStatus) -> QualityStatus:
    rank = {
        QualityStatus.PASS: 0,
        QualityStatus.WARN: 1,
        QualityStatus.QUARANTINE: 2,
        QualityStatus.REJECT: 3,
    }
    return second if rank[second] > rank[first] else first
