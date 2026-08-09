"""Raw-to-raw provider reconciliation for validation evidence before canonical normalization."""

from __future__ import annotations

from math import isclose

from trade_scout.data.reconciliation import (
    FieldDifference,
    RawValidationBar,
    ReconciliationResult,
    ReconciliationState,
    ReconciliationTolerance,
)


def compare_raw_validation_bars(
    primary: RawValidationBar,
    secondary: RawValidationBar | None,
    *,
    tolerance: ReconciliationTolerance,
) -> ReconciliationResult:
    """Compare explicitly linked raw provider bars without adjustment-field assumptions."""

    if secondary is None:
        return ReconciliationResult(
            instrument_id=primary.instrument_id,
            trade_date=primary.trade_date.isoformat(),
            primary_provider_id=primary.provider_id,
            secondary_provider_id=None,
            state=ReconciliationState.NOT_COMPARABLE,
            differences=(),
        )
    if (
        primary.instrument_id != secondary.instrument_id
        or primary.trade_date != secondary.trade_date
    ):
        return ReconciliationResult(
            instrument_id=primary.instrument_id,
            trade_date=primary.trade_date.isoformat(),
            primary_provider_id=primary.provider_id,
            secondary_provider_id=secondary.provider_id,
            state=ReconciliationState.NOT_COMPARABLE,
            differences=(),
            decision_note="instrument/date identity differs between raw comparison records",
        )

    differences = tuple(
        difference
        for difference in (
            _difference_if_needed(
                "open_raw",
                primary.open_raw,
                secondary.open_raw,
                absolute=tolerance.price_absolute,
                relative=tolerance.price_relative,
            ),
            _difference_if_needed(
                "high_raw",
                primary.high_raw,
                secondary.high_raw,
                absolute=tolerance.price_absolute,
                relative=tolerance.price_relative,
            ),
            _difference_if_needed(
                "low_raw",
                primary.low_raw,
                secondary.low_raw,
                absolute=tolerance.price_absolute,
                relative=tolerance.price_relative,
            ),
            _difference_if_needed(
                "close_raw",
                primary.close_raw,
                secondary.close_raw,
                absolute=tolerance.price_absolute,
                relative=tolerance.price_relative,
            ),
            _difference_if_needed(
                "volume_raw",
                primary.volume_raw,
                secondary.volume_raw,
                absolute=tolerance.volume_absolute,
                relative=tolerance.volume_relative,
            ),
        )
        if difference is not None
    )
    return ReconciliationResult(
        instrument_id=primary.instrument_id,
        trade_date=primary.trade_date.isoformat(),
        primary_provider_id=primary.provider_id,
        secondary_provider_id=secondary.provider_id,
        state=ReconciliationState.AGREE if not differences else ReconciliationState.UNRESOLVED,
        differences=differences,
    )


def _difference_if_needed(
    field: str,
    primary: float,
    secondary: float,
    *,
    absolute: float,
    relative: float,
) -> FieldDifference | None:
    if isclose(primary, secondary, rel_tol=relative, abs_tol=absolute):
        return None
    difference = abs(primary - secondary)
    denominator = max(abs(primary), abs(secondary))
    return FieldDifference(
        field=field,
        primary_value=primary,
        secondary_value=secondary,
        absolute_difference=difference,
        relative_difference=difference / denominator if denominator else None,
    )
