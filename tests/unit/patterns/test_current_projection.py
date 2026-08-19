from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.patterns.current_projection import project_latest_consolidation_state


def _bar(
    index: int,
    *,
    close: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    volume: float = 100.0,
    eligibility: bool = True,
    quality_status: QualityStatus = QualityStatus.PASS,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_projection"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
        eligibility=eligibility,
        quality_status=quality_status,
        dataset_version=DatasetVersion("projection-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _config(*, min_volume_ratio: float | None = None) -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
        min_breakout_volume_ratio=min_volume_ratio,
        volume_lookback_sessions=5,
    )


def test_projection_reports_canonical_breakout() -> None:
    bars = (*(_bar(index) for index in range(5)), _bar(5, close=103.0, high=104.0, low=101.0))

    projection = project_latest_consolidation_state(bars, _config())

    assert projection.status == "BREAKOUT"
    assert projection.latest_event_id is not None
    assert projection.trigger_boundary == 102.0
    assert projection.pattern_instance_id is not None


def test_projection_reports_volume_gate_failure_without_inventing_event() -> None:
    bars = (
        *(_bar(index) for index in range(5)),
        _bar(5, close=103.0, high=104.0, low=101.0, volume=150.0),
    )

    projection = project_latest_consolidation_state(bars, _config(min_volume_ratio=2.0))

    assert projection.status == "VOLUME_FILTER_FAIL"
    assert projection.latest_event_id is None
    assert projection.breakout_volume_ratio == 1.5
    assert projection.trigger_boundary == 102.0


def test_projection_reports_quality_invalidation() -> None:
    bars = (*(_bar(index) for index in range(5)), _bar(5, quality_status=QualityStatus.REJECT))

    projection = project_latest_consolidation_state(bars, _config())

    assert projection.status == "QUALITY_BLOCKED"
    assert projection.latest_event_id is None


def test_projection_is_prefix_invariant_to_future_bars() -> None:
    prefix = (*(_bar(index) for index in range(5)), _bar(5, close=103.0, high=104.0, low=101.0))
    extended = (*prefix, _bar(6, close=80.0, high=81.0, low=79.0))

    prefix_projection = project_latest_consolidation_state(prefix, _config())
    repeated_prefix_projection = project_latest_consolidation_state(extended[:6], _config())

    assert repeated_prefix_projection == prefix_projection
