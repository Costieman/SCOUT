from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.parameterized_expression import (
    extract_parameterized_specs,
    parse_parameterized_feature_name,
)
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    MovingAverageType,
    ParameterizedIndicatorSpec,
    compute_parameterized_indicator_frame,
)


def _bars(closes: tuple[float, ...]) -> tuple[DailyBar, ...]:
    return tuple(
        DailyBar(
            instrument_id=InstrumentId("tsi_parameterized"),
            trade_date=date(2024, 1, 2) + timedelta(days=index),
            open_raw=close,
            high_raw=close + 0.5,
            low_raw=close - 0.5,
            close_raw=close,
            volume_raw=1_000_000.0,
            split_factor=1.0,
            dividend_cash=0.0,
            open_split_adjusted=close,
            high_split_adjusted=close + 0.5,
            low_split_adjusted=close - 0.5,
            close_split_adjusted=close,
            provider_id="synthetic",
            dataset_version=DatasetVersion("parameterized-test-v1"),
            quality_status=QualityStatus.PASS,
        )
        for index, close in enumerate(closes)
    )


def _series(frame, feature_name: str):
    return tuple(item for item in frame if item.feature_name == feature_name)


def test_arbitrary_sma_and_ema_periods_are_materialized_point_in_time() -> None:
    bars = _bars((10.0, 11.0, 12.0, 13.0, 14.0))
    sma = ParameterizedIndicatorSpec(
        IndicatorFamily.MOVING_AVERAGE,
        IndicatorMetric.MA_DISTANCE_PCT,
        period=3,
    )
    ema = ParameterizedIndicatorSpec(
        IndicatorFamily.MOVING_AVERAGE,
        IndicatorMetric.MA_DISTANCE_PCT,
        period=3,
        moving_average_type=MovingAverageType.EMA,
    )

    frame = compute_parameterized_indicator_frame(bars, (sma, ema))
    sma_values = _series(frame, sma.feature_name)
    ema_values = _series(frame, ema.feature_name)

    assert sma_values[1].availability_status is FeatureAvailabilityStatus.WARMUP
    assert sma_values[2].value == pytest.approx((12.0 / 11.0 - 1.0) * 100.0)
    assert ema_values[2].value == pytest.approx((12.0 / 11.0 - 1.0) * 100.0)
    assert ema_values[3].value == pytest.approx((13.0 / 12.0 - 1.0) * 100.0)


def test_bollinger_band_distance_and_reach_use_resolved_parameters() -> None:
    bars = list(_bars((10.0, 12.0, 14.0, 15.0)))
    bars[2] = replace(bars[2], high_split_adjusted=16.0, high_raw=16.0)
    distance = ParameterizedIndicatorSpec(
        IndicatorFamily.BOLLINGER_BANDS,
        IndicatorMetric.BB_UPPER_DISTANCE_PCT,
        period=3,
        standard_deviations=2.0,
    )
    reached = ParameterizedIndicatorSpec(
        IndicatorFamily.BOLLINGER_BANDS,
        IndicatorMetric.BB_UPPER_REACHED,
        period=3,
        standard_deviations=2.0,
    )

    frame = compute_parameterized_indicator_frame(tuple(bars), (distance, reached))
    expected_upper = 12.0 + 2.0 * math.sqrt(8.0 / 3.0)

    assert _series(frame, distance.feature_name)[2].value == pytest.approx(
        (14.0 / expected_upper - 1.0) * 100.0
    )
    assert _series(frame, reached.feature_name)[2].value == 1.0
    assert reached.resolved_parameters["standard_deviations"] == 2.0
    assert reached.resolved_parameters["dispersion"] == "population_standard_deviation"


def test_bollinger_cross_uses_only_current_and_previous_completed_sessions() -> None:
    bars = _bars((10.0, 10.0, 10.0, 16.0, 9.0))
    spec = ParameterizedIndicatorSpec(
        IndicatorFamily.BOLLINGER_BANDS,
        IndicatorMetric.BB_UPPER_CROSS_UP,
        period=3,
        standard_deviations=1.0,
    )

    values = _series(compute_parameterized_indicator_frame(bars, (spec,)), spec.feature_name)

    assert values[3].value == 1.0
    changed = list(bars)
    changed[4] = replace(changed[4], close_split_adjusted=1_000.0, close_raw=1_000.0)
    changed_values = _series(
        compute_parameterized_indicator_frame(tuple(changed), (spec,)),
        spec.feature_name,
    )
    assert changed_values[3] == values[3]


def test_generated_feature_name_round_trips_and_expression_extracts_unique_specs() -> None:
    ma = ParameterizedIndicatorSpec(
        IndicatorFamily.MOVING_AVERAGE,
        IndicatorMetric.MA_CROSS_UP,
        period=37,
        moving_average_type=MovingAverageType.EMA,
    )
    bands = ParameterizedIndicatorSpec(
        IndicatorFamily.BOLLINGER_BANDS,
        IndicatorMetric.BB_MIDDLE_CROSS_UP,
        period=23,
        standard_deviations=2.5,
    )
    expression = f"({ma.feature_name} == 1 and {bands.feature_name} == 1) or {ma.feature_name} == 1"

    assert parse_parameterized_feature_name(ma.feature_name) == ma
    assert parse_parameterized_feature_name(bands.feature_name) == bands
    assert extract_parameterized_specs(expression) == (bands, ma)
