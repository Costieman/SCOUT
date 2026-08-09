from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import InstrumentId
from trade_scout.data.cross_provider_evidence import (
    CrossProviderEvidenceCase,
    evaluate_cross_provider_bars,
)
from trade_scout.data.provider import ProviderDailyBar
from trade_scout.data.reconciliation import ReconciliationState, ReconciliationTolerance


def _case() -> CrossProviderEvidenceCase:
    return CrossProviderEvidenceCase(
        case_id="abc-2020",
        instrument_id=InstrumentId("tsi_abc"),
        primary_provider_id="primary",
        primary_provider_instrument_id="primary:ABC",
        secondary_provider_id="secondary",
        secondary_provider_instrument_id="secondary:ABC",
        start=date(2020, 1, 2),
        end=date(2020, 1, 4),
    )


def _bar(provider: str, day: int, close: float, *, volume: float = 1000.0) -> ProviderDailyBar:
    return ProviderDailyBar(
        provider_id=provider,
        provider_instrument_id=f"{provider}:ABC",
        symbol="ABC",
        trade_date=date(2020, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
    )


def test_matching_raw_bars_agree_without_adjustment_metadata() -> None:
    report = evaluate_cross_provider_bars(
        _case(),
        primary_bars=(_bar("primary", 2, 10.0), _bar("primary", 3, 11.0)),
        secondary_bars=(_bar("secondary", 2, 10.0), _bar("secondary", 3, 11.0)),
        tolerance=ReconciliationTolerance(),
    )

    assert [result.state for result in report.results] == [
        ReconciliationState.AGREE,
        ReconciliationState.AGREE,
    ]
    assert report.summary.agreement_fraction_of_comparable == 1.0


def test_discrepancy_and_missing_sessions_are_preserved() -> None:
    report = evaluate_cross_provider_bars(
        _case(),
        primary_bars=(_bar("primary", 2, 10.0), _bar("primary", 3, 11.0)),
        secondary_bars=(_bar("secondary", 2, 10.5), _bar("secondary", 4, 12.0)),
        tolerance=ReconciliationTolerance(),
    )

    states = [result.state for result in report.results]
    assert states == [
        ReconciliationState.UNRESOLVED,
        ReconciliationState.NOT_COMPARABLE,
        ReconciliationState.NOT_COMPARABLE,
    ]
    assert report.summary.unresolved_count == 1
    assert report.summary.not_comparable_count == 2


def test_wrong_provider_identity_fails_before_comparison() -> None:
    wrong = ProviderDailyBar(
        provider_id="primary",
        provider_instrument_id="primary:OTHER",
        symbol="OTHER",
        trade_date=date(2020, 1, 2),
        open=10.0,
        high=10.0,
        low=10.0,
        close=10.0,
        volume=1000.0,
    )

    with pytest.raises(ValueError, match="wrong provider identity"):
        evaluate_cross_provider_bars(
            _case(),
            primary_bars=(wrong,),
            secondary_bars=(),
            tolerance=ReconciliationTolerance(),
        )
