from datetime import date, timedelta

from trade_scout.app import strategy_builder_service as service
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
)


def _bars(*, dataset: str = "indicator-cache-v1") -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(12):
        close = 100.0 + index
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_indicator_cache"),
                trade_date=date(2026, 1, 1) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=1_000_000.0,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion(dataset),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def _spec(period: int = 3) -> ParameterizedIndicatorSpec:
    return ParameterizedIndicatorSpec(
        family=IndicatorFamily.RSI,
        metric=IndicatorMetric.RSI_VALUE,
        period=period,
    )


def test_indicator_materialization_reuses_identical_upstream_stage() -> None:
    service._INDICATOR_CACHE.clear()
    before = service._INDICATOR_CACHE.stats()

    first, first_hit = service._materialize_requested_indicators(
        _bars(), (_spec(),), universe_id="reviewed_canonical"
    )
    second, second_hit = service._materialize_requested_indicators(
        _bars(), (_spec(),), universe_id="reviewed_canonical"
    )
    after = service._INDICATOR_CACHE.stats()

    assert first_hit is False
    assert second_hit is True
    assert first == second
    assert after.misses == before.misses + 1
    assert after.hits == before.hits + 1


def test_indicator_cache_invalidates_for_material_feature_change() -> None:
    service._INDICATOR_CACHE.clear()

    first, first_hit = service._materialize_requested_indicators(
        _bars(), (_spec(3),), universe_id="reviewed_canonical"
    )
    changed, changed_hit = service._materialize_requested_indicators(
        _bars(), (_spec(4),), universe_id="reviewed_canonical"
    )

    assert first_hit is False
    assert changed_hit is False
    assert first != changed


def test_indicator_cache_invalidates_for_dataset_revision() -> None:
    service._INDICATOR_CACHE.clear()

    service._materialize_requested_indicators(
        _bars(dataset="indicator-cache-v1"),
        (_spec(),),
        universe_id="reviewed_canonical",
    )
    _, revised_hit = service._materialize_requested_indicators(
        _bars(dataset="indicator-cache-v2"),
        (_spec(),),
        universe_id="reviewed_canonical",
    )

    assert revised_hit is False


def test_empty_parameterized_feature_set_does_not_materialize_or_store() -> None:
    service._INDICATOR_CACHE.clear()
    before = service._INDICATOR_CACHE.stats()

    values, cache_hit = service._materialize_requested_indicators(
        _bars(), (), universe_id="reviewed_canonical"
    )
    after = service._INDICATOR_CACHE.stats()

    assert values == ()
    assert cache_hit is True
    assert after.stores == before.stores
