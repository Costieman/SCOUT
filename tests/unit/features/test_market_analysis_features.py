from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.market_analysis import (
    MARKET_ANALYSIS_FEATURE_SET,
    MARKET_ANALYSIS_FEATURE_SET_VERSION,
    compute_incremental_market_analysis_feature_frame,
    compute_market_analysis_feature_frame,
)


def _bars(count: int = 260) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(count):
        close = 100.0 * math.exp(index * 0.001)
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_market_feature_test"),
                trade_date=date(2024, 1, 2) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=1_000.0 + index * 10.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("market-feature-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def _value(values, feature_name: str, index: int):
    feature_values = tuple(item for item in values if item.feature_name == feature_name)
    return feature_values[index]


def test_market_analysis_pack_registers_strategy_builder_features() -> None:
    names = {item.feature_name for item in MARKET_ANALYSIS_FEATURE_SET.definitions}
    assert MARKET_ANALYSIS_FEATURE_SET_VERSION == "market-analysis-features-v0.2"
    assert names == {
        "return_5",
        "return_20",
        "return_252",
        "realized_volatility_20",
        "relative_volume_20",
        "average_dollar_volume_20",
        "atr_pct_14",
        "distance_sma_20_pct",
        "distance_sma_50_pct",
        "distance_sma_200_pct",
        "sma_50_slope_20_pct",
        "sma_200_slope_20_pct",
        "sma_50_200_spread_pct",
        "sma_50_200_cross_up",
        "rsi_wilder_14",
        "macd_line_pct",
        "macd_signal_pct",
        "macd_histogram_pct",
        "macd_bullish_cross",
        "distance_prior_high_20_pct",
        "distance_prior_high_55_pct",
        "range_position_prior_20",
    }


def test_returns_are_point_in_time_and_use_split_adjusted_close() -> None:
    bars = _bars()
    values = compute_market_analysis_feature_frame(bars)
    five = _value(values, "return_5", 5)
    twenty = _value(values, "return_20", 20)
    annual = _value(values, "return_252", 252)
    assert five.availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert five.value == pytest.approx(
        bars[5].close_split_adjusted / bars[0].close_split_adjusted - 1
    )
    assert twenty.value == pytest.approx(
        bars[20].close_split_adjusted / bars[0].close_split_adjusted - 1
    )
    assert annual.value == pytest.approx(
        bars[252].close_split_adjusted / bars[0].close_split_adjusted - 1
    )


def test_relative_volume_and_dollar_volume_exclude_current_session() -> None:
    bars = list(_bars(25))
    bars[20] = replace(bars[20], volume_raw=10_000.0, close_raw=999.0)
    values = compute_market_analysis_feature_frame(tuple(bars))
    relative = _value(values, "relative_volume_20", 20)
    dollar_volume = _value(values, "average_dollar_volume_20", 20)
    expected_prior_mean = sum(item.volume_raw for item in bars[:20]) / 20
    expected_dollar_mean = sum(item.close_raw * item.volume_raw for item in bars[:20]) / 20
    assert relative.availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert relative.value == pytest.approx(10_000.0 / expected_prior_mean)
    assert dollar_volume.value == pytest.approx(expected_dollar_mean)


def test_prior_high_breakout_features_explicitly_exclude_current_session() -> None:
    bars = list(_bars(70))
    prior_high = max(item.high_split_adjusted for item in bars[30:50])
    assert prior_high is not None
    bars[50] = replace(
        bars[50],
        close_split_adjusted=prior_high * 1.02,
        high_split_adjusted=prior_high * 2.0,
    )
    values = compute_market_analysis_feature_frame(tuple(bars))
    breakout = _value(values, "distance_prior_high_20_pct", 50)
    position = _value(values, "range_position_prior_20", 50)
    assert breakout.value == pytest.approx(2.0)
    assert position.value is not None and position.value > 1.0


def test_rsi_macd_and_sma_trend_building_blocks_are_point_in_time() -> None:
    bars = _bars(240)
    values = compute_market_analysis_feature_frame(bars)

    rsi = _value(values, "rsi_wilder_14", 14)
    macd = _value(values, "macd_line_pct", 40)
    macd_signal = _value(values, "macd_signal_pct", 40)
    sma_slope = _value(values, "sma_50_slope_20_pct", 80)
    sma_spread = _value(values, "sma_50_200_spread_pct", 220)

    assert rsi.availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert rsi.value == pytest.approx(100.0)
    assert macd.value is not None and macd.value > 0
    assert macd_signal.value is not None and macd_signal.value > 0
    assert sma_slope.value is not None and sma_slope.value > 0
    assert sma_spread.value is not None and sma_spread.value > 0


def test_macd_bullish_cross_is_binary_and_uses_completed_close_history() -> None:
    bars = list(_bars(90))
    for index in range(45, 70):
        close = 112.0 - (index - 45) * 0.35
        bars[index] = replace(
            bars[index],
            open_raw=close,
            high_raw=close + 1.0,
            low_raw=close - 1.0,
            close_raw=close,
            open_split_adjusted=close,
            high_split_adjusted=close + 1.0,
            low_split_adjusted=close - 1.0,
            close_split_adjusted=close,
        )
    for index in range(70, 90):
        close = 104.0 + (index - 70) * 1.1
        bars[index] = replace(
            bars[index],
            open_raw=close,
            high_raw=close + 1.0,
            low_raw=close - 1.0,
            close_raw=close,
            open_split_adjusted=close,
            high_split_adjusted=close + 1.0,
            low_split_adjusted=close - 1.0,
            close_split_adjusted=close,
        )
    values = compute_market_analysis_feature_frame(tuple(bars))
    crosses = tuple(
        item
        for item in values
        if item.feature_name == "macd_bullish_cross"
        and item.availability_status is FeatureAvailabilityStatus.AVAILABLE
    )
    assert crosses
    assert {item.value for item in crosses} <= {0.0, 1.0}
    assert any(item.value == 1.0 for item in crosses)


def test_future_bar_changes_do_not_change_features_already_known_at_t() -> None:
    bars = _bars(100)
    baseline = compute_market_analysis_feature_frame(bars)
    altered = list(bars)
    altered[90] = replace(
        altered[90],
        high_split_adjusted=10_000.0,
        low_split_adjusted=1.0,
        close_split_adjusted=9_000.0,
        volume_raw=9_000_000.0,
    )
    second = compute_market_analysis_feature_frame(tuple(altered))
    baseline_at_80 = {
        item.feature_name: item.value for item in baseline if item.trade_date == bars[80].trade_date
    }
    second_at_80 = {
        item.feature_name: item.value for item in second if item.trade_date == bars[80].trade_date
    }
    assert baseline_at_80 == second_at_80


def test_incremental_market_analysis_matches_batch_for_new_rows() -> None:
    bars = _bars(260)
    history = bars[:250]
    new = bars[250:]
    incremental = compute_incremental_market_analysis_feature_frame(history, new)
    batch = compute_market_analysis_feature_frame(bars)
    new_dates = {item.trade_date for item in new}
    expected = tuple(item for item in batch if item.trade_date in new_dates)
    assert incremental == expected
