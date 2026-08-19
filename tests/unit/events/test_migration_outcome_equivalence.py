from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events import detect_consolidation_events
from trade_scout.outcomes.forward_returns import ForwardOutcome, measure_forward_outcomes
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
    detect_consolidation_breakouts,
)


def _bar(index: int, *, close: float, high: float, low: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_outcome_equivalence"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close - 0.25,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("outcome-equivalence-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _bars() -> tuple[ResearchBar, ...]:
    base = tuple(_bar(index, close=100.0, high=102.0, low=98.0) for index in range(5))
    signal = _bar(5, close=103.0, high=104.0, low=101.0)
    future = tuple(
        _bar(
            index,
            close=103.0 + (index - 5) * 0.75,
            high=104.0 + (index - 5) * 0.75,
            low=101.5 + (index - 5) * 0.50,
        )
        for index in range(6, 16)
    )
    return (*base, signal, *future)


def _outcome_identity(outcome: ForwardOutcome) -> tuple[object, ...]:
    return (
        outcome.instrument_id,
        outcome.horizon,
        outcome.entry_index,
        outcome.entry_date,
        outcome.entry_price,
        outcome.exit_date,
        outcome.exit_price,
        outcome.forward_return,
        outcome.mfe,
        outcome.mae,
        outcome.max_drawdown,
        outcome.dataset_version,
        outcome.outcome_definition_version,
    )


def test_typed_event_migration_preserves_forward_outcome_measurements() -> None:
    bars = _bars()
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )
    legacy_events = detect_consolidation_breakouts(bars, config)
    typed_events = detect_consolidation_events(bars, config)

    assert len(legacy_events) == len(typed_events) == 1
    assert legacy_events[0].signal_index == typed_events[0].signal_index
    assert legacy_events[0].signal_date == typed_events[0].signal_date

    legacy_outcomes = measure_forward_outcomes(bars, legacy_events, horizons=(2, 5, 10))
    typed_outcomes = measure_forward_outcomes(bars, typed_events, horizons=(2, 5, 10))

    assert [_outcome_identity(item) for item in typed_outcomes] == [
        _outcome_identity(item) for item in legacy_outcomes
    ]
    assert {item.event_id for item in typed_outcomes} != {item.event_id for item in legacy_outcomes}
    assert {item.outcome_definition_version for item in typed_outcomes} == {
        "next-open-forward-path-v0.1"
    }
