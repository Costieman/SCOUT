from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.outcomes.forward_returns import measure_forward_outcomes


@dataclass(frozen=True, slots=True)
class IndependentEvent:
    """Test event that deliberately has no dependency on a pattern implementation."""

    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str = "independent-test-event-v1"


def _bar(index: int) -> ResearchBar:
    price = 100.0 + index
    return ResearchBar(
        instrument_id=InstrumentId("tsi_contract"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=price,
        high=price + 2.0,
        low=price - 1.0,
        close=price + 1.0,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_outcome_engine_consumes_event_contract_without_pattern_type() -> None:
    bars = tuple(_bar(index) for index in range(5))
    event = IndependentEvent(
        event_id="independent-event",
        instrument_id=InstrumentId("tsi_contract"),
        signal_date=bars[0].trade_date,
        signal_index=0,
        dataset_version="test-v1",
    )

    outcomes = measure_forward_outcomes(bars, (event,), horizons=(2,))

    assert len(outcomes) == 1
    assert outcomes[0].event_id == "independent-event"
    assert outcomes[0].entry_index == 1
