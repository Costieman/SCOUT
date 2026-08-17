from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.app.entry_strategy_registry import EntryFamily, available_entry_strategies
from trade_scout.app.strategy_builder_service import StrategyBuilderRequest, StrategyBuilderService
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import TrendFilter


def _close(index: int) -> float:
    if index < 280:
        return 90.0 + index * 0.03
    if index < 300:
        return 100.0
    if index == 300:
        return 102.0
    return 102.0 + (index - 300) * 0.08


def _daily(index: int) -> DailyBar:
    close = _close(index)
    high = 101.0 if 280 <= index < 300 else close + 0.5
    low = 99.0 if 280 <= index < 300 else close - 0.5
    if index == 300:
        high = 102.5
        low = 100.5
    return DailyBar(
        instrument_id=InstrumentId("tsi_builder_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open_raw=close,
        high_raw=high,
        low_raw=low,
        close_raw=close,
        volume_raw=1_000_000.0 + index * 1_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=high,
        low_split_adjusted=low,
        close_split_adjusted=close,
        provider_id="synthetic",
        dataset_version=DatasetVersion("strategy-builder-test-v1"),
        quality_status=QualityStatus.PASS,
    )


def _research(item: DailyBar) -> ResearchBar:
    assert item.open_split_adjusted is not None
    assert item.high_split_adjusted is not None
    assert item.low_split_adjusted is not None
    assert item.close_split_adjusted is not None
    return ResearchBar(
        instrument_id=item.instrument_id,
        trade_date=item.trade_date,
        open=item.open_split_adjusted,
        high=item.high_split_adjusted,
        low=item.low_split_adjusted,
        close=item.close_split_adjusted,
        volume=item.volume_raw,
        eligibility=True,
        quality_status=item.quality_status,
        dataset_version=item.dataset_version,
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


@dataclass(frozen=True)
class _Source:
    daily: tuple[DailyBar, ...]

    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (UniverseOption("reviewed_canonical", "Synthetic reviewed cohort", False),)

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]:
        assert universe_id == "reviewed_canonical"
        return {"AAA": tuple(_research(item) for item in self.daily)}

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]:
        assert universe_id == "reviewed_canonical"
        return self.daily


def _source() -> _Source:
    return _Source(tuple(_daily(index) for index in range(330)))


def test_registry_exposes_feature_expression_and_consolidation_entries() -> None:
    families = tuple(item.family for item in available_entry_strategies())

    assert families == (EntryFamily.FEATURE_EXPRESSION, EntryFamily.CONSOLIDATION_BREAKOUT)


def test_feature_expression_signals_feed_common_exit_policy_engine() -> None:
    report = StrategyBuilderService(_source()).run(
        StrategyBuilderRequest(
            entry_family=EntryFamily.FEATURE_EXPRESSION,
            expression="return_20 > 0",
            rank_feature="return_20",
            per_session_limit=10,
            horizon=5,
            lookback_years=1,
            fixed_percentages=(0.05,),
            atr_multiples=(),
            trailing_percentages=(0.05,),
            trailing_atr_multiples=(),
        )
    )

    assert report.feature_strategy_report is not None
    assert report.consolidation_config is None
    assert report.entry_event_count > 0
    assert report.comparison.complete_event_count > 0
    assert len(report.comparison.policy_summaries) == 3
    assert {item.sample_size for item in report.comparison.policy_summaries} == {
        report.comparison.complete_event_count
    }
    assert report.provider_calls_made is False


def test_consolidation_entry_uses_same_exit_engine_without_feature_expression() -> None:
    report = StrategyBuilderService(_source()).run(
        StrategyBuilderRequest(
            entry_family=EntryFamily.CONSOLIDATION_BREAKOUT,
            horizon=5,
            lookback_years=1,
            duration=20,
            max_range_pct=0.03,
            trend_filter=TrendFilter.NONE,
            fixed_percentages=(0.05,),
            atr_multiples=(),
            trailing_percentages=(),
            trailing_atr_multiples=(),
        )
    )

    assert report.feature_strategy_report is None
    assert report.consolidation_config is not None
    assert report.entry_event_count >= 1
    assert report.comparison.complete_event_count >= 1
    assert len(report.comparison.policy_summaries) == 2
    assert {item.sample_size for item in report.comparison.policy_summaries} == {
        report.comparison.complete_event_count
    }
