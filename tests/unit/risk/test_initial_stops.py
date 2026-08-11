from __future__ import annotations

from dataclasses import replace
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
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutEvent,
    TrendFilter,
)
from trade_scout.risk.initial_stops import (
    CostModel,
    RiskExitReason,
    StopFamily,
    StopPolicy,
    evaluate_stop_policy,
    pre_entry_atr,
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
        instrument_id=InstrumentId("tsi_risk_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("risk-test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _event(signal_index: int = 20, duration: int = 10) -> ConsolidationBreakoutEvent:
    return ConsolidationBreakoutEvent(
        event_id="risk-test-event",
        instrument_id=InstrumentId("tsi_risk_test"),
        signal_date=date(2024, 1, 1) + timedelta(days=signal_index),
        signal_index=signal_index,
        formation_start=date(2024, 1, 1) + timedelta(days=signal_index - duration),
        formation_end=date(2024, 1, 1) + timedelta(days=signal_index - 1),
        boundary=101.0,
        signal_close=102.0,
        base_range_pct=0.03,
        duration=duration,
        trend_filter=TrendFilter.NONE,
        dataset_version="risk-test-v1",
    )


def _fixed(distance: float) -> StopPolicy:
    return StopPolicy(
        policy_id=f"fixed-{distance}",
        family=StopFamily.FIXED_PERCENT,
        parameters=MappingProxyType({"distance_pct": distance}),
    )


def _atr(multiple: float) -> StopPolicy:
    return StopPolicy(
        policy_id=f"atr-{multiple}",
        family=StopFamily.ATR,
        parameters=MappingProxyType({"atr_multiple": multiple}),
    )


def test_fixed_stop_touched_inside_daily_bar_fills_at_threshold() -> None:
    bars = [_bar(index) for index in range(25)]
    bars[20] = _bar(20, close=102.0, high=103.0, low=99.5)
    bars[21] = _bar(21, open_=100.0, high=103.0, low=94.0, close=96.0)
    bars[22] = _bar(22, open_=96.0, high=98.0, low=95.0, close=97.0)
    bars[23] = _bar(23, open_=97.0, high=99.0, low=96.0, close=98.0)

    result = evaluate_stop_policy(tuple(bars), _event(), horizon=3, policy=_fixed(0.05))

    assert result is not None
    assert result.exit_reason is RiskExitReason.STOP
    assert result.initial_stop == pytest.approx(95.0)
    assert result.assumed_exit_price == pytest.approx(95.0)
    assert result.realized_return == pytest.approx(-0.05)
    assert result.gap_through_stop is False
    assert result.holding_period_sessions == 1


def test_gap_through_stop_uses_open_not_nominal_stop() -> None:
    bars = [_bar(index) for index in range(26)]
    bars[20] = _bar(20, close=102.0, high=103.0, low=99.5)
    bars[21] = _bar(21, open_=100.0, high=102.0, low=98.0, close=101.0)
    bars[22] = _bar(22, open_=90.0, high=92.0, low=88.0, close=91.0)
    bars[23] = _bar(23, open_=91.0, high=94.0, low=90.0, close=93.0)

    result = evaluate_stop_policy(tuple(bars), _event(), horizon=3, policy=_fixed(0.05))

    assert result is not None
    assert result.gap_through_stop is True
    assert result.assumed_exit_price == pytest.approx(90.0)
    assert result.gap_loss_pct == pytest.approx(0.05)
    assert result.realized_return == pytest.approx(-0.10)


def test_atr_stop_uses_only_information_known_by_signal_close() -> None:
    bars = [_bar(index, high=101.0, low=99.0, close=100.0) for index in range(27)]
    bars[20] = _bar(20, close=102.0, high=103.0, low=101.0)
    bars[21] = _bar(21, open_=104.0, high=105.0, low=103.0, close=104.0)
    original = tuple(bars)
    altered = tuple(
        replace(item, high=500.0, low=1.0, close=400.0) if index >= 22 else item
        for index, item in enumerate(bars)
    )

    atr_before = pre_entry_atr(original, signal_index=20)
    first = evaluate_stop_policy(original, _event(), horizon=5, policy=_atr(2.0))
    second = evaluate_stop_policy(altered, _event(), horizon=5, policy=_atr(2.0))

    assert atr_before is not None
    assert first is not None and second is not None
    assert first.initial_stop == pytest.approx(second.initial_stop)
    assert first.initial_stop == pytest.approx(104.0 - 2.0 * atr_before)


def test_structural_base_low_comes_from_pre_signal_formation() -> None:
    bars = [_bar(index) for index in range(25)]
    for index in range(10, 20):
        bars[index] = _bar(index, high=101.0, low=97.5, close=100.0)
    bars[20] = _bar(20, close=102.0, high=103.0, low=100.0)
    bars[21] = _bar(21, open_=104.0, high=105.0, low=103.0, close=104.0)
    bars[22] = _bar(22, open_=104.0, high=105.0, low=103.0, close=104.0)
    bars[23] = _bar(23, open_=104.0, high=105.0, low=103.0, close=104.0)
    policy = StopPolicy(
        policy_id="structural-base-low",
        family=StopFamily.STRUCTURAL_BASE_LOW,
        parameters=MappingProxyType({}),
    )

    result = evaluate_stop_policy(tuple(bars), _event(), horizon=3, policy=policy)

    assert result is not None
    assert result.initial_stop == pytest.approx(97.5)
    assert result.stop_out is False


def test_stopped_recovery_is_retained_as_premature_stop_diagnostic() -> None:
    bars = [_bar(index) for index in range(25)]
    bars[20] = _bar(20, close=102.0, high=103.0, low=100.0)
    bars[21] = _bar(21, open_=100.0, high=102.0, low=94.0, close=96.0)
    bars[22] = _bar(22, open_=97.0, high=108.0, low=96.0, close=107.0)
    bars[23] = _bar(23, open_=107.0, high=112.0, low=106.0, close=110.0)

    result = evaluate_stop_policy(
        tuple(bars),
        _event(),
        horizon=3,
        policy=_fixed(0.05),
        cost_model=CostModel(),
    )

    assert result is not None
    assert result.stop_out is True
    assert result.premature_stop_flag is True
    assert result.no_stop_horizon_return == pytest.approx(0.10)
    assert result.post_stop_mfe is not None and result.post_stop_mfe > 0.10
