from datetime import date

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)
from trade_scout.data.reconciliation import (
    InvalidReconciliationDecisionError,
    ReconciliationState,
    ReconciliationTolerance,
    compare_daily_bars,
    record_reconciliation_decision,
)


def _bar(
    *,
    provider_id: str,
    close: float = 103.0,
    volume: int = 1_000_000,
    instrument_id: str = "inst-1",
    trade_date: date = date(2026, 8, 7),
) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=100.0,
        high_raw=105.0,
        low_raw=99.0,
        close_raw=close,
        volume_raw=volume,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=100.0,
        high_split_adjusted=105.0,
        low_split_adjusted=99.0,
        close_split_adjusted=close,
        provider_id=provider_id,
        dataset_version=DatasetVersion(f"{provider_id}-v1"),
        quality_status=QualityStatus.PASS,
    )


def test_values_within_tolerance_agree() -> None:
    result = compare_daily_bars(
        _bar(provider_id="primary"),
        _bar(provider_id="secondary", close=103.0005, volume=1_000_100),
        tolerance=ReconciliationTolerance(
            price_absolute=0.001,
            volume_absolute=200,
        ),
    )

    assert result.state is ReconciliationState.AGREE
    assert result.differences == ()


def test_price_and_volume_disagreement_is_unresolved_not_averaged() -> None:
    primary = _bar(provider_id="primary", close=103.0, volume=1_000_000)
    secondary = _bar(provider_id="secondary", close=104.0, volume=1_200_000)

    result = compare_daily_bars(
        primary,
        secondary,
        tolerance=ReconciliationTolerance(price_absolute=0.01, volume_relative=0.01),
    )

    assert result.state is ReconciliationState.UNRESOLVED
    assert {difference.field for difference in result.differences} == {"close_raw", "volume_raw"}
    assert primary.close_raw == 103.0
    assert secondary.close_raw == 104.0


def test_missing_secondary_record_is_not_comparable() -> None:
    result = compare_daily_bars(
        _bar(provider_id="primary"),
        None,
        tolerance=ReconciliationTolerance(),
    )

    assert result.state is ReconciliationState.NOT_COMPARABLE
    assert result.secondary_provider_id is None


def test_identity_mismatch_is_not_compared() -> None:
    result = compare_daily_bars(
        _bar(provider_id="primary"),
        _bar(provider_id="secondary", instrument_id="different"),
        tolerance=ReconciliationTolerance(),
    )

    assert result.state is ReconciliationState.NOT_COMPARABLE
    assert result.decision_note is not None


def test_review_can_explicitly_accept_primary_without_changing_values() -> None:
    result = compare_daily_bars(
        _bar(provider_id="primary", close=103.0),
        _bar(provider_id="secondary", close=104.0),
        tolerance=ReconciliationTolerance(),
    )

    reviewed = record_reconciliation_decision(
        result,
        state=ReconciliationState.PRIMARY_ACCEPTED,
        decision_note="secondary value conflicts with verified split record",
    )

    assert reviewed.state is ReconciliationState.PRIMARY_ACCEPTED
    assert reviewed.decision_note == "secondary value conflicts with verified split record"
    assert reviewed.differences == result.differences


def test_agreement_cannot_be_rewritten_as_error() -> None:
    result = compare_daily_bars(
        _bar(provider_id="primary"),
        _bar(provider_id="secondary"),
        tolerance=ReconciliationTolerance(),
    )

    with pytest.raises(InvalidReconciliationDecisionError):
        record_reconciliation_decision(
            result,
            state=ReconciliationState.SECONDARY_CONFIRMED_ERROR,
            decision_note="not permitted",
        )
