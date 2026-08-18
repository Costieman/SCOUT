from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.strategy_primitives import (
    StrategyPrimitiveFamily,
    StrategyPrimitiveMetric,
    StrategyPrimitiveSpec,
    compute_strategy_primitive_frame,
)


def _bar(index: int, *, close: float, width: float = 1.0) -> DailyBar:
    high = close + width / 2.0
    low = close - width / 2.0
    return DailyBar(
        instrument_id=InstrumentId("TEST"),
        trade_date=date(2026, 1, 1) + timedelta(days=index),
        open_raw=close,
        high_raw=high,
        low_raw=low,
        close_raw=close,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=high,
        low_split_adjusted=low,
        close_split_adjusted=close,
        provider_id="synthetic",
        dataset_version=DatasetVersion("synthetic-v1"),
        quality_status=QualityStatus.PASS,
    )


def test_nr7_marks_only_strictly_narrowest_current_range() -> None:
    bars = tuple(_bar(index, close=100.0 + index, width=1.0) for index in range(6)) + (
        _bar(6, close=106.0, width=0.25),
    )
    spec = StrategyPrimitiveSpec(
        family=StrategyPrimitiveFamily.NARROW_RANGE,
        metric=StrategyPrimitiveMetric.NARROW_RANGE_FLAG,
        period=7,
    )

    values = compute_strategy_primitive_frame(bars, (spec,))

    assert values[-1].availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert values[-1].value == 1.0
    assert all(item.value is None for item in values[:-1])


def test_bollinger_bandwidth_percentile_uses_only_trailing_information() -> None:
    closes = (10.0, 12.0, 8.0, 10.0, 10.0, 10.0)
    bars = tuple(_bar(index, close=close) for index, close in enumerate(closes))
    spec = StrategyPrimitiveSpec(
        family=StrategyPrimitiveFamily.BB_BANDWIDTH_PERCENTILE,
        metric=StrategyPrimitiveMetric.BB_BANDWIDTH_PERCENTILE,
        period=3,
        rank_period=4,
        standard_deviations=2.0,
    )

    values = compute_strategy_primitive_frame(bars, (spec,))

    assert values[-1].availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert values[-1].value == 25.0
    assert all(
        item.availability_status is FeatureAvailabilityStatus.WARMUP for item in values[:-1]
    )


def test_keltner_channel_materializes_point_in_time_bandwidth() -> None:
    bars = tuple(_bar(index, close=100.0 + index, width=2.0) for index in range(8))
    spec = StrategyPrimitiveSpec(
        family=StrategyPrimitiveFamily.KELTNER_CHANNEL,
        metric=StrategyPrimitiveMetric.KC_BANDWIDTH_PCT,
        period=3,
        multiplier=2.0,
    )

    values = compute_strategy_primitive_frame(bars, (spec,))

    available = [
        item for item in values if item.availability_status is FeatureAvailabilityStatus.AVAILABLE
    ]
    assert available
    assert all(item.value is not None and item.value > 0.0 for item in available)
    assert available[-1].resolved_parameters["center"] == "ema"
    assert available[-1].resolved_parameters["atr_smoothing"] == "wilder"


def test_strategy_primitives_reject_mixed_dataset_versions() -> None:
    first = _bar(0, close=100.0)
    second = DailyBar(
        instrument_id=first.instrument_id,
        trade_date=first.trade_date + timedelta(days=1),
        open_raw=101.0,
        high_raw=101.5,
        low_raw=100.5,
        close_raw=101.0,
        volume_raw=first.volume_raw,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=101.0,
        high_split_adjusted=101.5,
        low_split_adjusted=100.5,
        close_split_adjusted=101.0,
        provider_id="synthetic",
        dataset_version=DatasetVersion("synthetic-v2"),
        quality_status=QualityStatus.PASS,
    )
    spec = StrategyPrimitiveSpec(
        family=StrategyPrimitiveFamily.NARROW_RANGE,
        metric=StrategyPrimitiveMetric.NARROW_RANGE_FLAG,
        period=2,
    )

    try:
        compute_strategy_primitive_frame((first, second), (spec,))
    except ValueError as exc:
        assert "cannot mix canonical dataset versions" in str(exc)
    else:
        raise AssertionError("mixed dataset versions must fail closed")
