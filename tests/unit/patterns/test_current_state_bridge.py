from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
    current_consolidation_state,
)


def _bar(
    index: int,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
    quality_status: QualityStatus = QualityStatus.PASS,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_current_state"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=quality_status,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _config() -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=10,
        max_range_pct=0.03,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )


def test_current_breakout_uses_typed_prior_pattern_boundary() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
    )

    state = current_consolidation_state(bars, _config())

    assert state.state == "BREAKOUT"
    assert state.boundary == 101.0
    assert state.base_range_pct == (101.0 - 99.0) / 99.0


def test_current_state_rejects_non_pass_prior_pattern_window() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(9)]
        + [
            _bar(
                9,
                close=100.0,
                high=101.0,
                low=99.0,
                quality_status=QualityStatus.QUARANTINE,
            ),
            _bar(10, close=100.5, high=101.0, low=99.5),
        ]
    )

    state = current_consolidation_state(bars, _config())

    assert state.state == "NOT_QUALIFIED"
    assert "typed consolidation" in state.message
