from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.initial import (
    FeatureInputError,
    compute_incremental_initial_feature_frame,
    compute_initial_feature_frame,
    initial_feature_definition_sha256,
)

_DATASET = DatasetVersion("synthetic-canonical-v0.1")


def _bars(count: int) -> tuple[DailyBar, ...]:
    result: list[DailyBar] = []
    start = date(2020, 1, 1)
    for index in range(count):
        close = 100.0 + index
        result.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_feature_test"),
                trade_date=start + timedelta(days=index),
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
                dataset_version=_DATASET,
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(result)


def _value(
    values: tuple[object, ...],
    *,
    feature_name: str,
    index: int,
) -> object:
    from trade_scout.features.contracts import FeatureValue

    matches = [
        item
        for item in values
        if isinstance(item, FeatureValue)
        and item.feature_name == feature_name
        and item.trade_date == date(2020, 1, 1) + timedelta(days=index)
    ]
    assert len(matches) == 1
    return matches[0]


def test_initial_features_match_hand_calculated_examples() -> None:
    values = compute_initial_feature_frame(_bars(220))

    sma_50 = _value(values, feature_name="sma_50", index=49)
    sma_200 = _value(values, feature_name="sma_200", index=199)
    return_60 = _value(values, feature_name="return_60", index=60)
    dollar_volume = _value(values, feature_name="avg_dollar_volume_20", index=19)
    range_pct = _value(values, feature_name="rolling_range_pct_30", index=29)

    assert sma_50.value == pytest.approx(124.5)
    assert sma_200.value == pytest.approx(199.5)
    assert return_60.value == pytest.approx(0.6)
    assert dollar_volume.value == pytest.approx(sum(range(100, 120)) * 1000 / 20)
    assert range_pct.value == pytest.approx((130.0 - 99.0) / 129.0 * 100.0)

    warmup = _value(values, feature_name="sma_200", index=198)
    assert warmup.availability_status is FeatureAvailabilityStatus.WARMUP
    assert warmup.value is None


def test_future_changes_do_not_change_past_feature_values() -> None:
    original = _bars(90)
    altered = tuple(
        replace(
            bar,
            open_raw=bar.open_raw * 100,
            high_raw=bar.high_raw * 100,
            low_raw=bar.low_raw * 100,
            close_raw=bar.close_raw * 100,
            open_split_adjusted=bar.open_split_adjusted * 100 if bar.open_split_adjusted else None,
            high_split_adjusted=bar.high_split_adjusted * 100 if bar.high_split_adjusted else None,
            low_split_adjusted=bar.low_split_adjusted * 100 if bar.low_split_adjusted else None,
            close_split_adjusted=(
                bar.close_split_adjusted * 100 if bar.close_split_adjusted else None
            ),
        )
        if index > 70
        else bar
        for index, bar in enumerate(original)
    )

    first = compute_initial_feature_frame(original)
    second = compute_initial_feature_frame(altered)
    cutoff = original[70].trade_date
    assert tuple(item for item in first if item.trade_date <= cutoff) == tuple(
        item for item in second if item.trade_date <= cutoff
    )


def test_incremental_results_equal_batch_results_for_new_sessions() -> None:
    bars = _bars(90)
    history = bars[:75]
    new = bars[75:]

    incremental = compute_incremental_initial_feature_frame(history, new)
    batch = compute_initial_feature_frame(bars)
    new_keys = {(str(item.instrument_id), item.trade_date) for item in new}
    expected = tuple(
        item for item in batch if (str(item.instrument_id), item.trade_date) in new_keys
    )
    assert incremental == expected


def test_non_pass_canonical_input_fails_closed() -> None:
    bars = list(_bars(20))
    bars[5] = replace(bars[5], quality_status=QualityStatus.WARN)
    with pytest.raises(FeatureInputError, match="requires PASS input"):
        compute_initial_feature_frame(bars)


def test_missing_split_adjusted_input_is_explicitly_unavailable() -> None:
    bars = list(_bars(60))
    bars[49] = replace(bars[49], close_split_adjusted=None)
    values = compute_initial_feature_frame(bars)
    sma_50 = _value(values, feature_name="sma_50", index=49)
    assert sma_50.availability_status is FeatureAvailabilityStatus.INPUT_UNAVAILABLE
    assert sma_50.value is None


def test_definition_checksum_is_stable_sha256() -> None:
    digest = initial_feature_definition_sha256()
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
