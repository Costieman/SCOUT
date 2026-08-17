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
    evaluate_exit_policy,
    exit_policy_grid,
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
    # The entry-day high of 110 may tighten only the next session's stop to 104.5.
    assert result.market_exit_price == pytest.approx(104.5)
    assert result.exit_date == bars[22].trade_date.isoformat()
    assert result.holding_period_sessions == 2


def test_trailing_stop_does_not_invent_same_bar_high_before_low() -> None:
    bars = [_bar(index) for index in range(26)]
    # If high 110 were incorrectly applied before the same bar's low 96, a 5% trail would stop at
    # 104.5. The conservative daily-bar rule keeps the entry-session stop at 95.
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
