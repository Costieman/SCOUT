from __future__ import annotations

from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.initial import (
    ATR_FEATURE_NAME,
    ATR_FEATURE_VERSION,
    ATR_PERIOD,
    compute_initial_feature_frame,
)


def _bars(count: int) -> tuple[DailyBar, ...]:
    rows = []
    for index in range(count):
        close = 100.0 + index
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_atr_test"),
                trade_date=date(2024, 1, 1) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=1000.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("atr-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_registered_atr14_is_simple_mean_true_range_known_at_t() -> None:
    values = compute_initial_feature_frame(_bars(20))
    atr_values = tuple(item for item in values if item.feature_name == ATR_FEATURE_NAME)

    assert ATR_PERIOD == 14
    assert ATR_FEATURE_VERSION == "v0.1"
    assert atr_values[13].availability_status is FeatureAvailabilityStatus.WARMUP
    assert atr_values[13].value is None
    assert atr_values[14].availability_status is FeatureAvailabilityStatus.AVAILABLE
    assert atr_values[14].value == pytest.approx(2.0)
