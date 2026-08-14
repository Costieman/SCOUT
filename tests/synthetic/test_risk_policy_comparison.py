from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import InstrumentId
from trade_scout.events import replay_consolidation_pipeline
from trade_scout.patterns import PatternLifecycleState
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.risk import (
    PrematureStopDefinition,
    PrematureStopStatus,
    PrematureStopSuccessKind,
    StopFamily,
    StopPolicy,
    evaluate_stop_policy,
    run_risk_policy_comparison,
    structural_stop_context_from_pattern_state,
)
from trade_scout.synthetic import (
    ambiguous_daily_bar_scenario,
    consolidation_breakout_scenario,
    gap_down_scenario,
    stop_out_scenario,
)


@dataclass(frozen=True, slots=True)
class IndependentEvent:
    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str = "synthetic-risk-event-v1"


def _event_at(bars: tuple[object, ...], signal_index: int) -> IndependentEvent:
    bar = bars[signal_index]
    return IndependentEvent(
        event_id=f"synthetic-risk-{signal_index}",
        instrument_id=bar.instrument_id,
        signal_date=bar.trade_date,
        signal_index=signal_index,
        dataset_version=str(bar.dataset_version),
    )


def _fixed(distance: float = 0.05) -> StopPolicy:
    return StopPolicy(
        policy_id=f"fixed-{int(distance * 100)}pct-synthetic",
        family=StopFamily.FIXED_PERCENT,
        parameters=MappingProxyType({"distance_pct": distance}),
    )


def _no_stop() -> StopPolicy:
    return StopPolicy(
        policy_id="no-stop-synthetic",
        family=StopFamily.NO_STOP,
        parameters=MappingProxyType({}),
    )


def test_canonical_pattern_event_population_flows_into_all_risk_families() -> None:
    scenario = consolidation_breakout_scenario()
    config = ConsolidationBreakoutConfig(
        duration=20,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )
    replay = replay_consolidation_pipeline(scenario.raw_bars, config)

    assert len(replay.events) == 1
    event = replay.events[0]
    consumed = next(
        state
        for state in replay.pattern_states
        if state.state is PatternLifecycleState.CONSUMED
        and state.pattern_instance_id == event.pattern_instance_id
    )
    context = structural_stop_context_from_pattern_state(event, consumed)

    run = run_risk_policy_comparison(
        scenario.raw_bars,
        (event,),
        horizon=5,
        structural_contexts={event.event_id: context},
    )

    assert run.requested_event_ids == (event.event_id,)
    assert run.evaluated_event_ids == (event.event_id,)
    assert run.excluded_event_ids == ()
    assert {summary.stop_family for summary in run.comparison.policy_summaries} >= {
        StopFamily.NO_STOP,
        StopFamily.FIXED_PERCENT,
        StopFamily.ATR,
        StopFamily.STRUCTURAL_BASE_LOW,
        StopFamily.HYBRID_STRUCTURAL_ATR,
    }
    assert {summary.sample_size for summary in run.comparison.policy_summaries} == {1}
    assert len(run.comparison.event_population_fingerprint) == 64


def test_synthetic_gap_down_is_filled_at_gap_open_not_nominal_stop() -> None:
    scenario = gap_down_scenario()
    gap_date = scenario.annotations[0].start_date
    gap_index = next(
        index for index, bar in enumerate(scenario.raw_bars) if bar.trade_date == gap_date
    )
    event = _event_at(scenario.raw_bars, gap_index - 2)

    result = evaluate_stop_policy(
        scenario.raw_bars,
        event,
        horizon=2,
        policy=_fixed(),
    )

    assert result is not None
    assert result.gap_through_stop is True
    assert result.stop_trigger_date == gap_date.isoformat()
    assert result.assumed_exit_price == pytest.approx(scenario.raw_bars[gap_index].open)
    assert result.gap_loss_pct > 0


def test_same_bar_stop_and_success_threshold_remains_ambiguous() -> None:
    scenario = ambiguous_daily_bar_scenario()
    event = _event_at(scenario.raw_bars, 0)
    success = PrematureStopDefinition(
        definition_id="post-stop-plus-5pct-mfe",
        kind=PrematureStopSuccessKind.POST_STOP_MFE,
        threshold_return=0.05,
    )
    policies = (_no_stop(), _fixed())

    run = run_risk_policy_comparison(
        scenario.raw_bars,
        (event,),
        horizon=3,
        policies=policies,
        premature_success=success,
    )

    fixed_result = next(
        result for result in run.event_results if result.stop_family is StopFamily.FIXED_PERCENT
    )
    assert fixed_result.premature_stop_status is PrematureStopStatus.SAME_BAR_AMBIGUOUS
    assert "STOP_AND_SUCCESS_THRESHOLD_SAME_BAR_ORDER_UNKNOWN" in fixed_result.ambiguity_flags

    fixed_summary = next(
        summary
        for summary in run.comparison.policy_summaries
        if summary.stop_family is StopFamily.FIXED_PERCENT
    )
    assert fixed_summary.premature_stop_rate_lower_bound == 0.0
    assert fixed_summary.premature_stop_rate_upper_bound == 1.0
    assert fixed_summary.premature_stop_ambiguity_rate == 1.0


def test_stop_breach_followed_by_recovery_is_definite_premature_stop() -> None:
    scenario = stop_out_scenario()
    event = _event_at(scenario.raw_bars, 0)
    success = PrematureStopDefinition(
        definition_id="post-stop-plus-5pct-mfe",
        kind=PrematureStopSuccessKind.POST_STOP_MFE,
        threshold_return=0.05,
    )

    result = evaluate_stop_policy(
        scenario.raw_bars,
        event,
        horizon=11,
        policy=_fixed(),
        premature_success=success,
    )

    assert result is not None
    assert result.stop_out is True
    assert result.premature_stop_status is PrematureStopStatus.YES
    assert result.premature_stop_flag is True
    assert result.post_stop_mfe is not None and result.post_stop_mfe > 0.05
