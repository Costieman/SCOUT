from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from trade_scout.data.contracts import InstrumentId
from trade_scout.events import replay_consolidation_pipeline
from trade_scout.outcomes import ExtremeOrder, OutcomePathStatus, measure_outcome_paths
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.synthetic import (
    SyntheticAnnotationKind,
    ambiguous_daily_bar_scenario,
    consolidation_breakout_scenario,
    gap_down_scenario,
    stop_out_scenario,
)


@dataclass(frozen=True, slots=True)
class SyntheticEvent:
    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str = "synthetic-outcome-event-v1"


def _event_before_index(bars: tuple[object, ...], signal_index: int) -> SyntheticEvent:
    bar = bars[signal_index]
    return SyntheticEvent(
        event_id=f"synthetic-event-{signal_index}",
        instrument_id=bar.instrument_id,
        signal_date=bar.trade_date,
        signal_index=signal_index,
        dataset_version=str(bar.dataset_version),
    )


def test_pattern_event_flows_into_complete_outcome_path() -> None:
    scenario = consolidation_breakout_scenario()
    config = ConsolidationBreakoutConfig(
        duration=10,
        max_range_pct=0.04,
        trend_filter=TrendFilter.NONE,
    )
    replay = replay_consolidation_pipeline(scenario.raw_bars, config)

    assert len(replay.events) == 1
    event = replay.events[0]
    outcome = measure_outcome_paths(scenario.raw_bars, (event,), horizons=(5,))[0]

    assert outcome.status is OutcomePathStatus.COMPLETE
    assert outcome.event_id == event.event_id
    assert outcome.entry_index == event.signal_index + 1
    assert outcome.observed_sessions == 5
    assert outcome.forward_return is not None
    assert outcome.mfe is not None
    assert outcome.mae is not None


def test_stop_hit_does_not_terminate_unmanaged_outcome_path() -> None:
    scenario = stop_out_scenario()
    stop = next(
        annotation
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.STOP_HIT
    )
    event = _event_before_index(scenario.raw_bars, 0)

    outcome = measure_outcome_paths(scenario.raw_bars, (event,), horizons=(10,))[0]

    assert outcome.status is OutcomePathStatus.COMPLETE
    assert outcome.entry_price == pytest.approx(float(stop.values["entry_price"]))
    assert outcome.mae == pytest.approx(94.0 / 100.0 - 1.0)
    assert outcome.mae_date == stop.start_date
    assert outcome.time_to_mae_sessions == 3
    assert outcome.forward_return == pytest.approx(0.10)
    assert outcome.forward_return > 0


def test_gap_down_is_preserved_as_entry_and_path_gap_measurement() -> None:
    scenario = gap_down_scenario()
    gap = next(
        annotation
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.GAP_DOWN
    )
    gap_index = next(
        index for index, bar in enumerate(scenario.raw_bars) if bar.trade_date == gap.start_date
    )
    event = _event_before_index(scenario.raw_bars, gap_index - 1)

    outcome = measure_outcome_paths(scenario.raw_bars, (event,), horizons=(3,))[0]

    assert outcome.status is OutcomePathStatus.COMPLETE
    assert outcome.entry_date == gap.start_date
    assert outcome.entry_gap_return == pytest.approx(float(gap.values["gap_fraction"]))
    assert outcome.max_gap_down_return == pytest.approx(float(gap.values["gap_fraction"]))
    assert outcome.max_gap_down_date == gap.start_date


def test_daily_bar_extreme_order_and_drawdown_remain_explicitly_ambiguous() -> None:
    scenario = ambiguous_daily_bar_scenario()
    event = _event_before_index(scenario.raw_bars, 0)

    outcome = measure_outcome_paths(scenario.raw_bars, (event,), horizons=(1,))[0]

    assert outcome.status is OutcomePathStatus.COMPLETE
    assert outcome.mfe == pytest.approx(0.06)
    assert outcome.mae == pytest.approx(-0.06)
    assert outcome.time_to_mfe_sessions == 0
    assert outcome.time_to_mae_sessions == 0
    assert outcome.extreme_order is ExtremeOrder.SAME_BAR_AMBIGUOUS
    assert outcome.max_drawdown_lower_bound == pytest.approx(94.0 / 106.0 - 1.0)
    assert outcome.max_drawdown_upper_bound == pytest.approx(-0.06)
    assert outcome.intraday_drawdown_ambiguous is True
