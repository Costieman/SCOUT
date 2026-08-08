"""Deterministic snapshots for detecting provider revisions across retrieval times."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from trade_scout.data.provider import DailyBarRequest, ProviderAdapter, ProviderDailyBar


class CorrectionComparisonState(StrEnum):
    """Relationship between two snapshots of the same logical provider request."""

    IDENTICAL = "IDENTICAL"
    REVISED = "REVISED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class CorrectionProbeScopeError(ValueError):
    """Raised when provider output falls outside the declared correction-probe request."""


@dataclass(frozen=True, slots=True)
class DailyBarCorrectionSnapshot:
    """Logical checksum of one bounded provider-neutral daily-bar response."""

    provider_id: str
    start: str
    end: str
    provider_symbols: tuple[str, ...]
    record_count: int
    logical_sha256: str


@dataclass(frozen=True, slots=True)
class CorrectionComparison:
    """Auditable comparison of two correction snapshots."""

    state: CorrectionComparisonState
    baseline_sha256: str
    current_sha256: str
    detail: str


def capture_daily_bar_correction_snapshot(
    adapter: ProviderAdapter,
    request: DailyBarRequest,
) -> DailyBarCorrectionSnapshot:
    """Capture a deterministic logical hash without storing provider payload bytes in the snapshot."""

    if not request.provider_symbols:
        raise ValueError("correction probe requires explicit provider symbols")

    bars = tuple(adapter.get_daily_bars(request))
    _validate_scope(adapter.provider_id, request, bars)
    canonical_records = [_bar_record(bar) for bar in _sorted_bars(bars)]
    encoded = json.dumps(
        canonical_records,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    return DailyBarCorrectionSnapshot(
        provider_id=adapter.provider_id,
        start=request.start.isoformat(),
        end=request.end.isoformat(),
        provider_symbols=tuple(sorted(request.provider_symbols)),
        record_count=len(bars),
        logical_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def compare_daily_bar_correction_snapshots(
    baseline: DailyBarCorrectionSnapshot,
    current: DailyBarCorrectionSnapshot,
) -> CorrectionComparison:
    """Compare snapshots only when they represent the exact same logical request."""

    comparable = (
        baseline.provider_id == current.provider_id
        and baseline.start == current.start
        and baseline.end == current.end
        and baseline.provider_symbols == current.provider_symbols
    )
    if not comparable:
        return CorrectionComparison(
            state=CorrectionComparisonState.NOT_COMPARABLE,
            baseline_sha256=baseline.logical_sha256,
            current_sha256=current.logical_sha256,
            detail="provider, date window, or symbol scope differs",
        )

    identical = (
        baseline.logical_sha256 == current.logical_sha256
        and baseline.record_count == current.record_count
    )
    return CorrectionComparison(
        state=CorrectionComparisonState.IDENTICAL
        if identical
        else CorrectionComparisonState.REVISED,
        baseline_sha256=baseline.logical_sha256,
        current_sha256=current.logical_sha256,
        detail=(
            "logical provider records are unchanged"
            if identical
            else (
                "logical provider records changed: "
                f"count {baseline.record_count} -> {current.record_count}"
            )
        ),
    )


def _validate_scope(
    provider_id: str,
    request: DailyBarRequest,
    bars: tuple[ProviderDailyBar, ...],
) -> None:
    allowed_symbols = frozenset(request.provider_symbols or ())
    seen_keys: set[tuple[str, str]] = set()
    for bar in bars:
        if bar.provider_id != provider_id:
            raise CorrectionProbeScopeError(
                f"response provider {bar.provider_id} does not match adapter {provider_id}"
            )
        if bar.symbol not in allowed_symbols:
            raise CorrectionProbeScopeError(f"unexpected provider symbol {bar.symbol}")
        if not request.start <= bar.trade_date <= request.end:
            raise CorrectionProbeScopeError(
                f"bar date {bar.trade_date} falls outside {request.start}..{request.end}"
            )
        key = (bar.provider_instrument_id, bar.trade_date.isoformat())
        if key in seen_keys:
            raise CorrectionProbeScopeError(
                f"duplicate provider instrument/session observation {key[0]} {key[1]}"
            )
        seen_keys.add(key)


def _sorted_bars(bars: tuple[ProviderDailyBar, ...]) -> tuple[ProviderDailyBar, ...]:
    return tuple(
        sorted(
            bars,
            key=lambda bar: (
                bar.provider_id,
                bar.provider_instrument_id,
                bar.symbol,
                bar.trade_date,
            ),
        )
    )


def _bar_record(bar: ProviderDailyBar) -> dict[str, object]:
    return {
        "provider_id": bar.provider_id,
        "provider_instrument_id": bar.provider_instrument_id,
        "symbol": bar.symbol,
        "trade_date": bar.trade_date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "split_factor": bar.split_factor,
        "dividend_cash": bar.dividend_cash,
        "adjusted_open": bar.adjusted_open,
        "adjusted_high": bar.adjusted_high,
        "adjusted_low": bar.adjusted_low,
        "adjusted_close": bar.adjusted_close,
    }
