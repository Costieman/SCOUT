from __future__ import annotations

from datetime import date

from trade_scout.data.contracts import InstrumentId
from trade_scout.data.raw_reconciliation import compare_raw_validation_bars
from trade_scout.data.reconciliation import (
    RawValidationBar,
    ReconciliationState,
    ReconciliationTolerance,
)


def _bar(provider: str, close: float) -> RawValidationBar:
    return RawValidationBar(
        instrument_id=InstrumentId("tsi_abc"),
        provider_id=provider,
        provider_instrument_id=f"{provider}:ABC",
        trade_date=date(2020, 1, 2),
        open_raw=close,
        high_raw=close,
        low_raw=close,
        close_raw=close,
        volume_raw=1000.0,
    )


def test_raw_provider_bars_compare_without_adjustment_fields() -> None:
    result = compare_raw_validation_bars(
        _bar("primary", 10.0),
        _bar("secondary", 10.0),
        tolerance=ReconciliationTolerance(),
    )

    assert result.state is ReconciliationState.AGREE
    assert result.differences == ()


def test_raw_difference_remains_unresolved() -> None:
    result = compare_raw_validation_bars(
        _bar("primary", 10.0),
        _bar("secondary", 10.5),
        tolerance=ReconciliationTolerance(),
    )

    assert result.state is ReconciliationState.UNRESOLVED
    assert {item.field for item in result.differences} == {
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
    }
