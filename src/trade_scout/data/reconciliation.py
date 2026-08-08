"""Explicit cross-provider reconciliation without feed blending or automatic correction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from math import isclose

from trade_scout.data.contracts import DailyBar, InstrumentId
from trade_scout.data.provider import ProviderDailyBar


class ReconciliationState(StrEnum):
    """Cross-source resolution states defined by the ingestion specification."""

    AGREE = "AGREE"
    PRIMARY_ACCEPTED = "PRIMARY_ACCEPTED"
    SECONDARY_CONFIRMED_ERROR = "SECONDARY_CONFIRMED_ERROR"
    UNRESOLVED = "UNRESOLVED"
    NOT_COMPARABLE = "NOT_COMPARABLE"


@dataclass(frozen=True, slots=True)
class ReconciliationTolerance:
    """Independent price and volume tolerances for a provider comparison."""

    price_absolute: float = 0.0
    price_relative: float = 0.0
    volume_absolute: float = 0.0
    volume_relative: float = 0.0

    def __post_init__(self) -> None:
        if self.price_absolute < 0 or self.price_relative < 0:
            raise ValueError("price reconciliation tolerances must be non-negative")
        if self.volume_absolute < 0 or self.volume_relative < 0:
            raise ValueError("volume reconciliation tolerances must be non-negative")


@dataclass(frozen=True, slots=True)
class FieldDifference:
    """One observed provider discrepancy; values remain unmodified."""

    field: str
    primary_value: float | int
    secondary_value: float | int
    absolute_difference: float
    relative_difference: float | None


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Auditable comparison of one canonical primary bar with one validation bar."""

    instrument_id: InstrumentId
    trade_date: str
    primary_provider_id: str
    secondary_provider_id: str | None
    state: ReconciliationState
    differences: tuple[FieldDifference, ...]
    decision_note: str | None = None


@dataclass(frozen=True, slots=True)
class RawValidationBar:
    """Canonical-identity view of a secondary provider's raw OHLCV evidence."""

    instrument_id: InstrumentId
    provider_id: str
    provider_instrument_id: str
    trade_date: date
    open_raw: float
    high_raw: float
    low_raw: float
    close_raw: float
    volume_raw: float


class InvalidReconciliationDecisionError(ValueError):
    """Raised when review attempts to assign an invalid reconciliation state."""


class ValidationIdentityError(ValueError):
    """Raised when a raw validation record is linked with an invalid canonical identity."""


def raw_validation_bar(
    provider_bar: ProviderDailyBar,
    *,
    instrument_id: InstrumentId,
    expected_provider_instrument_id: str,
) -> RawValidationBar:
    """Link raw secondary evidence to canonical identity without normalizing adjustment fields."""

    if provider_bar.provider_instrument_id != expected_provider_instrument_id:
        raise ValidationIdentityError(
            "provider bar identity does not match the explicitly linked provider instrument ID"
        )
    return RawValidationBar(
        instrument_id=instrument_id,
        provider_id=provider_bar.provider_id,
        provider_instrument_id=provider_bar.provider_instrument_id,
        trade_date=provider_bar.trade_date,
        open_raw=provider_bar.open,
        high_raw=provider_bar.high,
        low_raw=provider_bar.low,
        close_raw=provider_bar.close,
        volume_raw=provider_bar.volume,
    )


def compare_daily_bars(
    primary: DailyBar,
    secondary: DailyBar | None,
    *,
    tolerance: ReconciliationTolerance,
) -> ReconciliationResult:
    """Compare canonical provider values; never average or replace either source."""

    if secondary is None:
        return _missing_secondary(primary)
    return _compare_raw_values(
        primary,
        secondary_instrument_id=secondary.instrument_id,
        secondary_trade_date=secondary.trade_date,
        secondary_provider_id=secondary.provider_id,
        secondary_open=secondary.open_raw,
        secondary_high=secondary.high_raw,
        secondary_low=secondary.low_raw,
        secondary_close=secondary.close_raw,
        secondary_volume=secondary.volume_raw,
        tolerance=tolerance,
    )


def compare_primary_to_raw_validation(
    primary: DailyBar,
    secondary: RawValidationBar | None,
    *,
    tolerance: ReconciliationTolerance,
) -> ReconciliationResult:
    """Compare canonical primary raw OHLCV with explicitly linked secondary raw evidence."""

    if secondary is None:
        return _missing_secondary(primary)
    return _compare_raw_values(
        primary,
        secondary_instrument_id=secondary.instrument_id,
        secondary_trade_date=secondary.trade_date,
        secondary_provider_id=secondary.provider_id,
        secondary_open=secondary.open_raw,
        secondary_high=secondary.high_raw,
        secondary_low=secondary.low_raw,
        secondary_close=secondary.close_raw,
        secondary_volume=secondary.volume_raw,
        tolerance=tolerance,
    )


def record_reconciliation_decision(
    result: ReconciliationResult,
    *,
    state: ReconciliationState,
    decision_note: str,
) -> ReconciliationResult:
    """Record an explicit reviewed decision without mutating either provider value."""

    allowed = {
        ReconciliationState.PRIMARY_ACCEPTED,
        ReconciliationState.SECONDARY_CONFIRMED_ERROR,
        ReconciliationState.UNRESOLVED,
    }
    if result.state is not ReconciliationState.UNRESOLVED or state not in allowed:
        raise InvalidReconciliationDecisionError(
            f"cannot resolve reconciliation state {result.state} as {state}"
        )
    if not decision_note.strip():
        raise ValueError("a reconciliation decision requires an audit note")
    return replace(result, state=state, decision_note=decision_note.strip())


def _missing_secondary(primary: DailyBar) -> ReconciliationResult:
    return ReconciliationResult(
        instrument_id=primary.instrument_id,
        trade_date=primary.trade_date.isoformat(),
        primary_provider_id=primary.provider_id,
        secondary_provider_id=None,
        state=ReconciliationState.NOT_COMPARABLE,
        differences=(),
    )


def _compare_raw_values(
    primary: DailyBar,
    *,
    secondary_instrument_id: InstrumentId,
    secondary_trade_date: date,
    secondary_provider_id: str,
    secondary_open: float,
    secondary_high: float,
    secondary_low: float,
    secondary_close: float,
    secondary_volume: float,
    tolerance: ReconciliationTolerance,
) -> ReconciliationResult:
    if (
        primary.instrument_id != secondary_instrument_id
        or primary.trade_date != secondary_trade_date
    ):
        return ReconciliationResult(
            instrument_id=primary.instrument_id,
            trade_date=primary.trade_date.isoformat(),
            primary_provider_id=primary.provider_id,
            secondary_provider_id=secondary_provider_id,
            state=ReconciliationState.NOT_COMPARABLE,
            differences=(),
            decision_note="instrument/date identity differs between comparison records",
        )

    differences = tuple(
        difference
        for difference in (
            _price_difference("open_raw", primary.open_raw, secondary_open, tolerance),
            _price_difference("high_raw", primary.high_raw, secondary_high, tolerance),
            _price_difference("low_raw", primary.low_raw, secondary_low, tolerance),
            _price_difference("close_raw", primary.close_raw, secondary_close, tolerance),
            _volume_difference(primary.volume_raw, secondary_volume, tolerance),
        )
        if difference is not None
    )
    state = ReconciliationState.AGREE if not differences else ReconciliationState.UNRESOLVED
    return ReconciliationResult(
        instrument_id=primary.instrument_id,
        trade_date=primary.trade_date.isoformat(),
        primary_provider_id=primary.provider_id,
        secondary_provider_id=secondary_provider_id,
        state=state,
        differences=differences,
    )


def _price_difference(
    field: str,
    primary: float,
    secondary: float,
    tolerance: ReconciliationTolerance,
) -> FieldDifference | None:
    if isclose(
        primary,
        secondary,
        rel_tol=tolerance.price_relative,
        abs_tol=tolerance.price_absolute,
    ):
        return None
    return _difference(field, primary, secondary)


def _volume_difference(
    primary: float,
    secondary: float,
    tolerance: ReconciliationTolerance,
) -> FieldDifference | None:
    if isclose(
        primary,
        secondary,
        rel_tol=tolerance.volume_relative,
        abs_tol=tolerance.volume_absolute,
    ):
        return None
    return _difference("volume_raw", primary, secondary)


def _difference(field: str, primary: float | int, secondary: float | int) -> FieldDifference:
    absolute = abs(float(primary) - float(secondary))
    denominator = max(abs(float(primary)), abs(float(secondary)))
    relative = absolute / denominator if denominator else None
    return FieldDifference(
        field=field,
        primary_value=primary,
        secondary_value=secondary,
        absolute_difference=absolute,
        relative_difference=relative,
    )
