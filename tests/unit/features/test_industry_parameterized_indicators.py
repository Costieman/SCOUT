from __future__ import annotations

from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.parameterized_expression import parse_parameterized_feature_name
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
    compute_parameterized_indicator_frame,
)


def _bars(count: int = 320) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(count):
        close = 100.0 + index * 0.2 + (index % 7) * 0.05
        volume = 1_000_000.0 + index * 2_000.0
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_industry_indicators"),
                trade_date=date(2024, 1, 2) + timedelta(days=index),
                open_raw=close - 0.1,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=volume,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close - 0.1,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("industry-indicator-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def _last_value(spec: ParameterizedIndicatorSpec) -> float:
    frame = compute_parameterized_indicator_frame(_bars(), (spec,))
    value = frame[-1].value
    assert value is not None
    return value


@pytest.mark.parametrize(
    ("family", "metric", "period"),
    (
        (IndicatorFamily.PRICE_ROC, IndicatorMetric.ROC_PCT, 37),
        (IndicatorFamily.RSI, IndicatorMetric.RSI_VALUE, 21),
        (IndicatorFamily.ATR, IndicatorMetric.ATR_PCT, 18),
        (IndicatorFamily.RELATIVE_VOLUME, IndicatorMetric.RVOL, 33),
        (
            IndicatorFamily.AVERAGE_DOLLAR_VOLUME,
            IndicatorMetric.AVERAGE_DOLLAR_VOLUME,
            25,
        ),
        (
            IndicatorFamily.HISTORICAL_VOLATILITY,
            IndicatorMetric.HISTORICAL_VOLATILITY_PCT,
            42,
        ),
        (IndicatorFamily.PRIOR_HIGH, IndicatorMetric.PRIOR_HIGH_DISTANCE_PCT, 55),
    ),
)
def test_industry_indicator_periods_are_operator_parameterized(
    family: IndicatorFamily,
    metric: IndicatorMetric,
    period: int,
) -> None:
    spec = ParameterizedIndicatorSpec(family, metric, period=period)

    assert _last_value(spec) == pytest.approx(_last_value(parse_parameterized_feature_name(spec.feature_name)))
    assert spec.resolved_parameters["period"] == period
    assert spec.resolved_parameters["timeframe"] == "daily"


def test_macd_periods_round_trip_and_cross_output_is_binary() -> None:
    line = ParameterizedIndicatorSpec(
        IndicatorFamily.MACD,
        IndicatorMetric.MACD_LINE_PCT,
        period=35,
        fast_period=8,
        slow_period=35,
        signal_period=5,
    )
    cross = ParameterizedIndicatorSpec(
        IndicatorFamily.MACD,
        IndicatorMetric.MACD_CROSS_UP,
        period=35,
        fast_period=8,
        slow_period=35,
        signal_period=5,
    )

    assert parse_parameterized_feature_name(line.feature_name) == line
    assert parse_parameterized_feature_name(cross.feature_name) == cross
    frame = compute_parameterized_indicator_frame(_bars(), (line, cross))
    cross_values = [item.value for item in frame if item.feature_name == cross.feature_name and item.value is not None]
    assert cross_values
    assert set(cross_values) <= {0.0, 1.0}


def test_atr_uses_wilder_smoothing_and_reports_percent_of_price() -> None:
    spec = ParameterizedIndicatorSpec(IndicatorFamily.ATR, IndicatorMetric.ATR_PCT, period=14)

    value = _last_value(spec)

    assert value > 0
    assert spec.resolved_parameters["smoothing"] == "wilder"
    assert spec.units == "percent"
