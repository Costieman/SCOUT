from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.strategy_builder_service import StrategyBuilderRequest, StrategyBuilderService
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
)


def _daily(index: int) -> DailyBar:
    close = 50.0 + index * 0.02
    return DailyBar(
        instrument_id=InstrumentId("tsi_windowed_builder"),
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
        dataset_version=DatasetVersion("strategy-builder-windowed-v1"),
        quality_status=QualityStatus.PASS,
    )


@dataclass(frozen=True)
class _WindowedSource:
    daily: tuple[DailyBar, ...]

    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (UniverseOption("reviewed_canonical", "Synthetic reviewed cohort", False),)

    def research_series(self, universe_id: str):
        raise AssertionError("windowed Strategy Builder path must not load full research_series")

    def canonical_daily_bars(self, universe_id: str):
        raise AssertionError("windowed Strategy Builder path must not load all canonical bars")

    def strategy_builder_latest_trade_date(self, universe_id: str) -> date:
        assert universe_id == "reviewed_canonical"
        return self.daily[-1].trade_date

    def strategy_builder_dataset_record_count(self, universe_id: str) -> int:
        assert universe_id == "reviewed_canonical"
        return len(self.daily)

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        assert universe_id == "reviewed_canonical"
        before = tuple(item for item in self.daily if item.trade_date < signal_start)
        warmup = before[-warmup_observations:]
        active = tuple(
            item for item in self.daily if signal_start <= item.trade_date <= signal_end
        )
        return (*warmup, *active)


def test_windowed_source_skips_full_history_loads() -> None:
    source = _WindowedSource(tuple(_daily(index) for index in range(1_200)))
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

    assert report.performance.dataset_daily_bar_count == 1_200
    assert 0 < report.performance.canonical_daily_bar_count < 1_200
    assert report.performance.working_daily_bar_count == report.performance.canonical_daily_bar_count
    assert report.feature_strategy_report is not None
    assert report.feature_strategy_report.outcomes == ()
    assert report.comparison.complete_event_count > 0
