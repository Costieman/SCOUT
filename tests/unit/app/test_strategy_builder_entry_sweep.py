from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import cast

import pytest

from trade_scout.app.strategy_builder_entry_sweep import (
    EntrySweepParameter,
    StrategyBuilderEntrySweepService,
    materialize_entry_sweep_values,
)
from trade_scout.app.strategy_builder_service import StrategyBuilderRequest, StrategyBuilderSource
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus


def _bars(count: int = 180) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(count):
        close = 100.0 + index * 0.35
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("rising"),
                trade_date=date(2024, 1, 2) + timedelta(days=index),
                open_raw=close,
                high_raw=close + 1.0,
                low_raw=close - 1.0,
                close_raw=close,
                volume_raw=1_000_000.0 + index,
                split_factor=1.0,
                dividend_cash=0.0,
                open_split_adjusted=close,
                high_split_adjusted=close + 1.0,
                low_split_adjusted=close - 1.0,
                close_split_adjusted=close,
                provider_id="synthetic",
                dataset_version=DatasetVersion("entry-sweep-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class _WindowSource:
    rows: tuple[DailyBar, ...]

    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (
            UniverseOption(
                universe_id="reviewed_canonical",
                label="Synthetic reviewed universe",
                point_in_time_membership=False,
            ),
        )

    def strategy_builder_latest_trade_date(self, universe_id: str) -> date:
        assert universe_id == "reviewed_canonical"
        return self.rows[-1].trade_date

    def strategy_builder_dataset_record_count(self, universe_id: str) -> int:
        assert universe_id == "reviewed_canonical"
        return len(self.rows)

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        assert universe_id == "reviewed_canonical"
        assert signal_start <= signal_end
        assert warmup_observations >= 1
        return self.rows


def test_materialize_entry_sweep_values_is_inclusive_and_deterministic() -> None:
    periods = materialize_entry_sweep_values(
        start=20,
        end=60,
        step=10,
        parameter=EntrySweepParameter.PERIOD,
    )
    deviations = materialize_entry_sweep_values(
        start=1.0,
        end=2.0,
        step=0.25,
        parameter=EntrySweepParameter.STANDARD_DEVIATIONS,
    )

    assert periods == (20.0, 30.0, 40.0, 50.0, 60.0)
    assert deviations == (1.0, 1.25, 1.5, 1.75, 2.0)


def test_period_sweep_rejects_fractional_trading_days() -> None:
    with pytest.raises(ValueError, match="whole trading-day"):
        materialize_entry_sweep_values(
            start=20,
            end=21,
            step=0.5,
            parameter=EntrySweepParameter.PERIOD,
        )


def test_entry_sweep_builds_separate_point_in_time_child_populations() -> None:
    source = cast(StrategyBuilderSource, _WindowSource(_bars()))
    request = StrategyBuilderRequest(
        lookback_years=1,
        horizon=5,
        expression="pi__moving_average__ma_distance_pct__close__p20__sma > 0",
        rank_feature="return_20",
        per_session_limit=500,
        fixed_percentages=(),
        trailing_percentages=(),
        atr_multiples=(),
        trailing_atr_multiples=(),
        entry_slippage_bps=5,
        exit_slippage_bps=5,
        stop_slippage_bps=10,
    )

    report = StrategyBuilderEntrySweepService(source).run(
        request,
        target_feature_name="pi__moving_average__ma_distance_pct__close__p20__sma",
        parameter=EntrySweepParameter.PERIOD,
        values=(10.0, 20.0, 30.0),
    )

    assert report.values == (10.0, 20.0, 30.0)
    assert report.parameter_label == "Moving Average period"
    assert report.unit_label == "trading days"
    assert len(report.search_space_fingerprint) == 64
    assert [item.resolved_feature_name for item in report.points] == [
        "pi__moving_average__ma_distance_pct__close__p10__sma",
        "pi__moving_average__ma_distance_pct__close__p20__sma",
        "pi__moving_average__ma_distance_pct__close__p30__sma",
    ]
    assert all(item.entry_event_count > 0 for item in report.points)
    assert all(item.complete_event_count > 0 for item in report.points)
    assert all(item.expectancy is not None and item.expectancy > 0 for item in report.points)
    assert report.research_state == "EXPLORATORY"
