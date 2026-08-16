from __future__ import annotations

from dataclasses import dataclass
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
from trade_scout.risk import (
    CostModel,
    StopFamily,
    StopPolicy,
    StructuralStopContext,
    evaluate_stop_policy,
    pre_entry_atr,
)


@dataclass(frozen=True, slots=True)
class IndependentEvent:
    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    dataset_version: str
    event_definition_version: str = "independent-risk-event-v1"


def _bar(
    index: int,
    *,
    open_: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    close: float = 100.0,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi-risk-harness"),
        trade_date=date(2024, 1, 2) + timedelta(days=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("risk-harness-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _event(bars: tuple[ResearchBar, ...], signal_index: int = 20) -> IndependentEvent:
    return IndependentEvent(
        event_id="risk-harness-event",
        instrument_id=bars[signal_index].instrument_id,
        signal_date=bars[signal_index].trade_date,
        signal_index=signal_index,
        dataset_version=str(bars[signal_index].dataset_version),
    )


def test_stop_cost_hooks_include_commission_and_stop_slippage() -> None:
    bars = [_bar(index) for index in range(25)]
    bars[20] = _bar(20, high=103.0, low=99.0, close=102.0)
    bars[21] = _bar(21, open_=100.0, high=101.0, low=94.0, close=96.0)
    bars[22] = _bar(22, open_=96.0, high=98.0, low=95.0, close=97.0)
    policy = StopPolicy(
        policy_id="fixed-5pct-costed",
        family=StopFamily.FIXED_PERCENT,
        parameters=MappingProxyType({"distance_pct": 0.05}),
    )
    costs = CostModel(
        entry_slippage_bps=10.0,
        exit_slippage_bps=10.0,
        stop_slippage_bps=20.0,
        commission_bps_per_side=5.0,
    )

    result = evaluate_stop_policy(
        tuple(bars), _event(tuple(bars)), horizon=2, policy=policy, cost_model=costs
    )

    assert result is not None
    assert result.assumed_entry_price == pytest.approx(100.0 * 1.0015)
    assert result.assumed_exit_price == pytest.approx(95.0 * 0.9965)
    assert result.gross_realized_return == pytest.approx(-0.05)
    assert result.realized_return < result.gross_realized_return
    assert result.cost_drag_return > 0


def test_hybrid_stop_uses_wider_of_structure_and_pre_entry_atr() -> None:
    bars = [_bar(index) for index in range(25)]
    bars[20] = _bar(20, high=103.0, low=99.0, close=102.0)
    bars[21] = _bar(21, open_=104.0, high=105.0, low=101.0, close=104.0)
    bars[22] = _bar(22, open_=104.0, high=106.0, low=100.0, close=105.0)
    series = tuple(bars)
    event = _event(series)
    atr = pre_entry_atr(series, signal_index=20)
    assert atr is not None
    context = StructuralStopContext(
        event_id=event.event_id,
        formation_start=series[10].trade_date,
        formation_end=series[19].trade_date,
        support=97.5,
        resistance=101.0,
        dataset_version=event.dataset_version,
    )
    policy = StopPolicy(
        policy_id="hybrid-test",
        family=StopFamily.HYBRID_STRUCTURAL_ATR,
        parameters=MappingProxyType({"atr_multiple": 2.0}),
    )

    result = evaluate_stop_policy(
        series,
        event,
        horizon=2,
        policy=policy,
        structural_context=context,
    )

    assert result is not None
    assert result.initial_stop == pytest.approx(min(97.5, 104.0 - 2.0 * atr))
