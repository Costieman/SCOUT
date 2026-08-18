from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutEvent, TrendFilter
from trade_scout.risk.exit_policies import (
    ExitFamily,
    ExitPolicy,
    ExitReason,
    ManagedExitPlan,
    SameBarExitPolicy,
    TargetFamily,
    evaluate_exit_policy,
    exit_policy_grid,
    managed_exit_policy_grid,
)


def _bar(
    index: int,
    *,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_exit_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("exit-test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _event(signal_index: int = 20) -> ConsolidationBreakoutEvent:
    return ConsolidationBreakoutEvent(
        event_id="exit-test-event",
        instrument_id=InstrumentId("tsi_exit_test"),
        signal_date=date(2024, 1, 1) + timedelta(days=signal_index),
        signal_index=signal_index,
        formation_start=date(2024, 1, 11),
        formation_end=date(2024, 1, 20),
        boundary=101.0,
        signal_close=102.0,
        base_range_pct=0.03,
        duration=10,
        trend_filter=TrendFilter.NONE,
        dataset_version="exit-test-v1",
    )


def _policy(family: ExitFamily, **parameters: float) -> ExitPolicy:
    return ExitPolicy(
        policy_id=f"test-{family.value}",
        family=family,
        parameters=MappingProxyType(parameters),
    )


def _managed(
    *,
    stop_family: ExitFamily = ExitFamily.FIXED_PERCENT_STOP,
    stop_value: float = 0.05,
    target_family: TargetFamily | None = TargetFamily.FIXED_PERCENT,
    target_value: float | None = 0.10,
    same_bar_policy: SameBarExitPolicy = SameBarExitPolicy.STOP_FIRST,
) -> ExitPolicy:
    policies = managed_exit_policy_grid(
        (
            ManagedExitPlan(
                stop_family=stop_family,
                stop_value=stop_value,
                target_family=target_family,
                target_value=target_value,
                same_bar_policy=same_bar_policy,
            ),
        )
    )
    return policies[1]


def test_fixed_percent_stop_matches_expected_threshold_fill() -> None:
    bars = [_bar(index) for index in range(26)]
    bars[21] = _bar(21, open_=100.0, high=102.0, low=94.0, close=96.0)
    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_policy(ExitFamily.FIXED_PERCENT_STOP, distance_pct=0.05),
    )

    assert result is not None
    assert result.exit_reason is ExitReason.STOP
    assert result.initial_stop == pytest.approx(95.0)
    assert result.market_exit_price == pytest.approx(95.0)
    assert result.realized_return == pytest.approx(-0.05)


def test_trailing_percent_ratchets_only_for_next_session() -> None:
    bars = [_bar(index) for index in range(27)]
    bars[21] = _bar(21, open_=100.0, high=110.0, low=96.0, close=109.0)
    bars[22] = _bar(22, open_=109.0, high=111.0, low=103.0, close=104.0)
    bars[23] = _bar(23, open_=104.0, high=105.0, low=102.0, close=103.0)
    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_policy(ExitFamily.TRAILING_PERCENT_STOP, distance_pct=0.05),
    )

    assert result is not None
    assert result.exit_reason is ExitReason.STOP
    assert result.market_exit_price == pytest.approx(104.5)
    assert result.exit_date == bars[22].trade_date.isoformat()
    assert result.holding_period_sessions == 2


def test_trailing_stop_does_not_invent_same_bar_high_before_low() -> None:
    bars = [_bar(index) for index in range(26)]
    bars[21] = _bar(21, open_=100.0, high=110.0, low=96.0, close=109.0)
    bars[22] = _bar(22, open_=109.0, high=110.0, low=108.0, close=109.0)
    bars[23] = _bar(23, open_=109.0, high=110.0, low=108.0, close=109.0)
    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_policy(ExitFamily.TRAILING_PERCENT_STOP, distance_pct=0.05),
    )

    assert result is not None
    assert result.exit_reason is ExitReason.RESEARCH_HORIZON
    assert result.holding_period_sessions == 3


def test_fixed_stop_plus_fixed_target_exits_at_target_first() -> None:
    bars = [_bar(index) for index in range(26)]
    bars[21] = _bar(21, open_=100.0, high=111.0, low=99.0, close=108.0)

    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_managed(),
    )

    assert result is not None
    assert result.exit_reason is ExitReason.TARGET
    assert result.initial_stop == pytest.approx(95.0)
    assert result.initial_target == pytest.approx(110.0)
    assert result.market_exit_price == pytest.approx(110.0)
    assert result.targeted is True
    assert result.stopped is False


def test_trailing_stop_can_be_paired_with_atr_profit_target() -> None:
    bars = [_bar(index) for index in range(28)]
    bars[21] = _bar(21, open_=100.0, high=105.0, low=99.0, close=104.0)

    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=5,
        policy=_managed(
            stop_family=ExitFamily.TRAILING_PERCENT_STOP,
            stop_value=0.08,
            target_family=TargetFamily.ATR_MULTIPLE,
            target_value=2.0,
        ),
    )

    assert result is not None
    assert result.exit_reason is ExitReason.TARGET
    assert result.initial_stop == pytest.approx(92.0)
    assert result.initial_target == pytest.approx(104.0)
    assert result.market_exit_price == pytest.approx(104.0)


def test_same_bar_stop_and_target_are_flagged_and_policy_driven() -> None:
    bars = [_bar(index) for index in range(26)]
    bars[21] = _bar(21, open_=100.0, high=112.0, low=94.0, close=105.0)

    stop_first = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_managed(same_bar_policy=SameBarExitPolicy.STOP_FIRST),
    )
    target_first = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_managed(same_bar_policy=SameBarExitPolicy.TARGET_FIRST),
    )

    assert stop_first is not None and target_first is not None
    assert stop_first.exit_reason is ExitReason.STOP
    assert stop_first.market_exit_price == pytest.approx(95.0)
    assert target_first.exit_reason is ExitReason.TARGET
    assert target_first.market_exit_price == pytest.approx(110.0)
    assert stop_first.same_bar_stop_target_ambiguous is True
    assert target_first.same_bar_stop_target_ambiguous is True


def test_gap_above_target_is_known_before_later_intraday_stop_touch() -> None:
    bars = [_bar(index) for index in range(27)]
    bars[21] = _bar(21, open_=100.0, high=104.0, low=99.0, close=102.0)
    bars[22] = _bar(22, open_=112.0, high=113.0, low=94.0, close=100.0)

    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=4,
        policy=_managed(same_bar_policy=SameBarExitPolicy.STOP_FIRST),
    )

    assert result is not None
    assert result.exit_reason is ExitReason.TARGET
    assert result.market_exit_price == pytest.approx(112.0)
    assert result.same_bar_stop_target_ambiguous is False


def test_r_multiple_target_uses_initial_protective_risk() -> None:
    bars = [_bar(index) for index in range(26)]
    bars[21] = _bar(21, open_=100.0, high=111.0, low=99.0, close=108.0)

    result = evaluate_exit_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_managed(target_family=TargetFamily.R_MULTIPLE, target_value=2.0),
    )

    assert result is not None
    assert result.initial_stop == pytest.approx(95.0)
    assert result.initial_target == pytest.approx(110.0)
    assert result.exit_reason is ExitReason.TARGET


def test_managed_grid_keeps_explicit_plans_and_hold_control_without_cartesian_search() -> None:
    plans = (
        ManagedExitPlan(
            stop_family=ExitFamily.TRAILING_PERCENT_STOP,
            stop_value=0.08,
            target_family=TargetFamily.FIXED_PERCENT,
            target_value=0.15,
        ),
        ManagedExitPlan(
            stop_family=ExitFamily.ATR_STOP,
            stop_value=2.0,
            target_family=TargetFamily.R_MULTIPLE,
            target_value=3.0,
        ),
    )

    policies = managed_exit_policy_grid(plans)

    assert len(policies) == 3
    assert policies[0].family is ExitFamily.HOLD_TO_HORIZON
    assert policies[1].target_family is TargetFamily.FIXED_PERCENT
    assert policies[2].target_family is TargetFamily.R_MULTIPLE


def test_custom_policy_grid_is_configuration_not_code() -> None:
    policies = exit_policy_grid(
        fixed_percentages=(0.02,),
        atr_multiples=(),
        trailing_percentages=(0.03, 0.05),
        trailing_atr_multiples=(),
    )

    assert tuple(item.family for item in policies) == (
        ExitFamily.HOLD_TO_HORIZON,
        ExitFamily.FIXED_PERCENT_STOP,
        ExitFamily.TRAILING_PERCENT_STOP,
        ExitFamily.TRAILING_PERCENT_STOP,
    )
    assert policies[1].parameters["distance_pct"] == pytest.approx(0.02)
    assert policies[2].parameters["distance_pct"] == pytest.approx(0.03)
    assert policies[3].parameters["distance_pct"] == pytest.approx(0.05)
