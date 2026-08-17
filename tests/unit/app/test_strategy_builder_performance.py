from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.app.entry_strategy_registry import EntryFamily
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
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
)


def _daily(index: int) -> DailyBar:
    close = 50.0 + index * 0.02
    return DailyBar(
        instrument_id=InstrumentId("tsi_builder_perf"),
        trade_date=date(2022, 1, 1) + timedelta(days=index),
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
        dataset_version=DatasetVersion("strategy-builder-perf-v1"),
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


def test_builder_bounds_feature_history_and_skips_duplicate_outcome_measurement() -> None:
    source = _Source(tuple(_daily(index) for index in range(1_200)))
    ma = ParameterizedIndicatorSpec(
        IndicatorFamily.MOVING_AVERAGE,
        IndicatorMetric.MA_DISTANCE_PCT,
        period=200,
    )

    report = StrategyBuilderService(source).run(
        StrategyBuilderRequest(
            entry_family=EntryFamily.FEATURE_EXPRESSION,
            expression=f"{ma.feature_name} > 0",
            rank_feature="return_20",
            per_session_limit=500,
            horizon=5,
            lookback_years=1,
            fixed_percentages=(),
            atr_multiples=(),
            trailing_percentages=(0.10,),
            trailing_atr_multiples=(),
        )
    )

    assert report.feature_strategy_report is not None
    assert report.feature_strategy_report.outcomes == ()
    assert report.feature_strategy_report.summaries == ()
    assert report.performance.canonical_daily_bar_count == 1_200
    assert 0 < report.performance.working_daily_bar_count < 1_200
    assert report.performance.working_daily_bar_count <= 600
    phase_names = {name for name, _ in report.performance.phase_seconds}
    assert {
        "load research universe",
        "load canonical daily bars",
        "bound working history",
        "materialize requested indicators",
        "select frozen entry population",
        "evaluate exit policies",
        "summarize research results",
    } <= phase_names
    assert report.performance.total_seconds >= 0
