from __future__ import annotations

from datetime import date

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events import event_from_pattern_state
from trade_scout.patterns import PatternLifecycleState, PatternState


def _pattern(*, state: PatternLifecycleState = PatternLifecycleState.QUALIFIED) -> PatternState:
    return PatternState(
        pattern_instance_id="tsi_test:consolidation-v1:2024-01-01:2024-01-20",
        instrument_id=InstrumentId("tsi_test"),
        pattern_family="consolidation",
        pattern_version="1.0.0",
        as_of_date=date(2024, 1, 20),
        state=state,
        formation_start=date(2024, 1, 1),
        formation_end=date(2024, 1, 20),
        resolved_parameters={"duration": 20, "max_range_pct": 0.1},
        structural_boundaries={"resistance": 105.0, "support": 95.0},
        feature_set_version="features-v1",
        dataset_version="dataset-v1",
        quality_status=QualityStatus.PASS,
    )


def _bar(*, close: float = 106.0, instrument: str = "tsi_test") -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId(instrument),
        trade_date=date(2024, 1, 21),
        open=104.0,
        high=max(107.0, close),
        low=103.0,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("dataset-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_qualified_pattern_can_emit_close_breakout_event() -> None:
    event = event_from_pattern_state(_pattern(), _bar(), signal_index=20)

    assert event is not None
    assert event.pattern_instance_id == _pattern().pattern_instance_id
    assert event.trigger_boundary == 105.0
    assert event.trigger_value == 106.0
    assert event.signal_index == 20


def test_close_at_or_below_boundary_does_not_emit_event() -> None:
    assert event_from_pattern_state(_pattern(), _bar(close=105.0), signal_index=20) is None


def test_nonqualified_pattern_does_not_emit_event() -> None:
    assert (
        event_from_pattern_state(
            _pattern(state=PatternLifecycleState.FORMING),
            _bar(),
            signal_index=20,
        )
        is None
    )


def test_pattern_and_signal_instrument_must_match() -> None:
    with pytest.raises(ValueError, match="same instrument"):
        event_from_pattern_state(_pattern(), _bar(instrument="other"), signal_index=20)
