from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events.consolidation_pipeline import (
    consolidation_event_cache_stats,
    detect_consolidation_events,
    reset_consolidation_event_cache,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter


def _bar(index: int, *, dataset: str = "daily-v1") -> ResearchBar:
    close = 100.0 if index < 30 else 103.0 + (index - 30) * 0.1
    return ResearchBar(
        instrument_id=InstrumentId("cache-test"),
        trade_date=date(2025, 1, 1) + timedelta(days=index),
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion(dataset),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _bars(*, dataset: str = "daily-v1") -> tuple[ResearchBar, ...]:
    return tuple(_bar(index, dataset=dataset) for index in range(45))


def _config(*, duration: int = 20) -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=duration,
        max_range_pct=0.04,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
        min_breakout_volume_ratio=None,
        volume_lookback_sessions=20,
    )


def test_detect_consolidation_events_reuses_identical_replay() -> None:
    reset_consolidation_event_cache()

    first = detect_consolidation_events(_bars(), _config())
    second = detect_consolidation_events(_bars(), _config())

    assert first == second
    stats = consolidation_event_cache_stats()
    assert stats.misses == 1
    assert stats.hits == 1


def test_config_change_invalidates_event_cache() -> None:
    reset_consolidation_event_cache()

    detect_consolidation_events(_bars(), _config(duration=20))
    detect_consolidation_events(_bars(), _config(duration=25))

    stats = consolidation_event_cache_stats()
    assert stats.misses == 2
    assert stats.hits == 0


def test_dataset_change_invalidates_event_cache() -> None:
    reset_consolidation_event_cache()

    detect_consolidation_events(_bars(dataset="daily-v1"), _config())
    detect_consolidation_events(_bars(dataset="daily-v2"), _config())

    stats = consolidation_event_cache_stats()
    assert stats.misses == 2
    assert stats.hits == 0
