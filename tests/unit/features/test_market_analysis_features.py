from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.market_analysis import (
    MARKET_ANALYSIS_FEATURE_SET,
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


def test_market_analysis_pack_registers_core_strategy_features() -> None:
    names = {item.feature_name for item in MARKET_ANALYSIS_FEATURE_SET.definitions}
    assert names == {
        "return_5",
        "return_20",
        "return_252",
        "realized_volatility_20",
        "relative_volume_20",
        "atr_pct_14",
        "distance_sma_50_pct",
        "distance_sma_200_pct",
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


def test_relative_volume_20_excludes_current_session_from_baseline() -> None:
    bars = list(_bars(25))
    bars[20] = replace(bars[20], volume_raw=10_000.0)
    values = compute_market_analysis_feature_frame(tuple(bars))
    relative = _value(values, "relative_volume_20", 20)
    expected_prior_mean = sum(item.volume_raw for item in bars[:20]) / 20
    assert relative.availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert relative.value == pytest.approx(10_000.0 / expected_prior_mean)


def test_future_bar_changes_do_not_change_features_already_known_at_t() -> None:
    bars = _bars(80)
    baseline = compute_market_analysis_feature_frame(bars)
    altered = list(bars)
    altered[70] = replace(
        altered[70],
        high_split_adjusted=10_000.0,
        low_split_adjusted=1.0,
        close_split_adjusted=9_000.0,
        volume_raw=9_000_000.0,
    )
    second = compute_market_analysis_feature_frame(tuple(altered))
    baseline_at_60 = {
        item.feature_name: item.value for item in baseline if item.trade_date == bars[60].trade_date
    }
    second_at_60 = {
        item.feature_name: item.value for item in second if item.trade_date == bars[60].trade_date
    }
    assert baseline_at_60 == second_at_60


def test_incremental_market_analysis_matches_batch_for_new_rows() -> None:
    bars = _bars(260)
    history = bars[:250]
    new = bars[250:]
    incremental = compute_incremental_market_analysis_feature_frame(history, new)
    batch = compute_market_analysis_feature_frame(bars)
    new_dates = {item.trade_date for item in new}
    expected = tuple(item for item in batch if item.trade_date in new_dates)
    assert incremental == expected
