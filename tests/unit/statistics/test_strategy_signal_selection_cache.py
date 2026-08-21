from datetime import date, timedelta

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    reset_signal_selection_cache,
    run_feature_strategy_research,
    signal_selection_cache_stats,
)


def _bar(index: int, *, dataset: str = "daily-v1") -> DailyBar:
    close = 100.0 + index * 0.2
    return DailyBar(
        instrument_id=InstrumentId("signal-cache-test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
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
        dataset_version=DatasetVersion(dataset),
        quality_status=QualityStatus.PASS,
    )


def _bars(*, dataset: str = "daily-v1") -> tuple[DailyBar, ...]:
    return tuple(_bar(index, dataset=dataset) for index in range(260))


def _strategy(*, expression: str = "return_20 > 0") -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="cache-test",
        name="Cache test",
        expression=expression,
        rank_feature="return_20",
        per_session_limit=10,
    )


def test_signal_only_research_reuses_identical_entry_population() -> None:
    reset_signal_selection_cache()
    before = signal_selection_cache_stats()

    first = run_feature_strategy_research(
        _bars(), strategy=_strategy(), horizons=(20,), measure_outcomes=False
    )
    second = run_feature_strategy_research(
        _bars(), strategy=_strategy(), horizons=(20,), measure_outcomes=False
    )

    assert first == second
    after = signal_selection_cache_stats()
    assert after.misses - before.misses == 1
    assert after.hits - before.hits == 1


def test_strategy_change_invalidates_signal_population() -> None:
    reset_signal_selection_cache()
    before = signal_selection_cache_stats()

    run_feature_strategy_research(
        _bars(), strategy=_strategy(expression="return_20 > 0"), horizons=(20,), measure_outcomes=False
    )
    run_feature_strategy_research(
        _bars(), strategy=_strategy(expression="return_20 > 0.05"), horizons=(20,), measure_outcomes=False
    )

    after = signal_selection_cache_stats()
    assert after.misses - before.misses == 2
    assert after.hits - before.hits == 0


def test_dataset_change_invalidates_signal_population() -> None:
    reset_signal_selection_cache()
    before = signal_selection_cache_stats()

    run_feature_strategy_research(
        _bars(dataset="daily-v1"), strategy=_strategy(), horizons=(20,), measure_outcomes=False
    )
    run_feature_strategy_research(
        _bars(dataset="daily-v2"), strategy=_strategy(), horizons=(20,), measure_outcomes=False
    )

    after = signal_selection_cache_stats()
    assert after.misses - before.misses == 2
    assert after.hits - before.hits == 0


def test_full_outcome_research_does_not_use_signal_only_cache() -> None:
    reset_signal_selection_cache()
    before = signal_selection_cache_stats()

    run_feature_strategy_research(_bars(), strategy=_strategy(), horizons=(5,), measure_outcomes=True)

    after = signal_selection_cache_stats()
    assert after.misses == before.misses
    assert after.hits == before.hits
