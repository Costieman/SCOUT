"""Bounded cross-provider raw-OHLCV evidence without feed blending or automatic repair."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.reconciliation import (
    ReconciliationResult,
    ReconciliationTolerance,
    compare_primary_to_raw_validation,
    raw_validation_bar,
)
from trade_scout.data.reconciliation_evidence import (
    ReconciliationEvidenceSummary,
    summarize_reconciliation_evidence,
)


@dataclass(frozen=True, slots=True)
class CrossProviderEvidenceCase:
    """Explicit identity and date scope for one provider comparison sample."""

    case_id: str
    instrument_id: InstrumentId
    primary_provider_id: str
    primary_provider_instrument_id: str
    secondary_provider_id: str
    secondary_provider_instrument_id: str
    start: date
    end: date

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("cross-provider evidence case_id must be non-empty")
        if self.end < self.start:
            raise ValueError("cross-provider evidence end must be on or after start")
        for value in (
            self.primary_provider_id,
            self.primary_provider_instrument_id,
            self.secondary_provider_id,
            self.secondary_provider_instrument_id,
        ):
            if not value.strip():
                raise ValueError("cross-provider evidence identities must be non-empty")


@dataclass(frozen=True, slots=True)
class CrossProviderEvidenceReport:
    """Raw provider comparison results plus aggregate coverage/discrepancy evidence."""

    case: CrossProviderEvidenceCase
    results: tuple[ReconciliationResult, ...]
    summary: ReconciliationEvidenceSummary


def evaluate_cross_provider_bars(
    case: CrossProviderEvidenceCase,
    *,
    primary_bars: tuple[ProviderDailyBar, ...],
    secondary_bars: tuple[ProviderDailyBar, ...],
    tolerance: ReconciliationTolerance,
) -> CrossProviderEvidenceReport:
    """Compare matching sessions through explicit permanent provider identities.

    Missing secondary sessions remain NOT_COMPARABLE. Extra secondary sessions are represented by
    a NOT_COMPARABLE result rather than discarded. Provider values are never averaged or replaced.
    """

    primary = _validated_bars(
        primary_bars,
        provider_id=case.primary_provider_id,
        provider_instrument_id=case.primary_provider_instrument_id,
        start=case.start,
        end=case.end,
    )
    secondary = _validated_bars(
        secondary_bars,
        provider_id=case.secondary_provider_id,
        provider_instrument_id=case.secondary_provider_instrument_id,
        start=case.start,
        end=case.end,
    )
    primary_by_date = {bar.trade_date: bar for bar in primary}
    secondary_by_date = {bar.trade_date: bar for bar in secondary}
    if len(primary_by_date) != len(primary):
        raise ValueError("primary comparison sample contains duplicate trading dates")
    if len(secondary_by_date) != len(secondary):
        raise ValueError("secondary comparison sample contains duplicate trading dates")

    results: list[ReconciliationResult] = []
    all_dates = sorted(set(primary_by_date) | set(secondary_by_date))
    for trade_date in all_dates:
        primary_bar = primary_by_date.get(trade_date)
        secondary_bar = secondary_by_date.get(trade_date)
        if primary_bar is None:
            results.append(
                ReconciliationResult(
                    instrument_id=case.instrument_id,
                    trade_date=trade_date.isoformat(),
                    primary_provider_id=case.primary_provider_id,
                    secondary_provider_id=case.secondary_provider_id,
                    state="NOT_COMPARABLE",  # type: ignore[arg-type]
                    differences=(),
                    decision_note="secondary provider has a session absent from primary sample",
                )
            )
            continue
        canonical_primary = _primary_bar(case.instrument_id, primary_bar)
        raw_secondary = (
            raw_validation_bar(
                secondary_bar,
                instrument_id=case.instrument_id,
                expected_provider_instrument_id=case.secondary_provider_instrument_id,
            )
            if secondary_bar is not None
            else None
        )
        results.append(
            compare_primary_to_raw_validation(
                canonical_primary,
                raw_secondary,
                tolerance=tolerance,
            )
        )

    frozen = tuple(results)
    return CrossProviderEvidenceReport(
        case=case,
        results=frozen,
        summary=summarize_reconciliation_evidence(frozen),
    )


def _validated_bars(
    bars: tuple[ProviderDailyBar, ...],
    *,
    provider_id: str,
    provider_instrument_id: str,
    start: date,
    end: date,
) -> tuple[ProviderDailyBar, ...]:
    for bar in bars:
        if bar.provider_id != provider_id:
            raise ValueError("cross-provider evidence sample contains the wrong provider")
        if bar.provider_instrument_id != provider_instrument_id:
            raise ValueError("cross-provider evidence sample contains the wrong provider identity")
        if not start <= bar.trade_date <= end:
            raise ValueError("cross-provider evidence sample contains an out-of-scope date")
    return tuple(sorted(bars, key=lambda item: item.trade_date))


def _primary_bar(instrument_id: InstrumentId, bar: ProviderDailyBar) -> DailyBar:
    return DailyBar(
        instrument_id=instrument_id,
        trade_date=bar.trade_date,
        open_raw=bar.open,
        high_raw=bar.high,
        low_raw=bar.low,
        close_raw=bar.close,
        volume_raw=bar.volume,
        split_factor=bar.split_factor if bar.split_factor is not None else 1.0,
        dividend_cash=bar.dividend_cash if bar.dividend_cash is not None else 0.0,
        open_split_adjusted=bar.adjusted_open,
        high_split_adjusted=bar.adjusted_high,
        low_split_adjusted=bar.adjusted_low,
        close_split_adjusted=bar.adjusted_close,
        provider_id=bar.provider_id,
        dataset_version=DatasetVersion("cross-provider-evidence-runtime"),
        quality_status=QualityStatus.PASS,
    )
