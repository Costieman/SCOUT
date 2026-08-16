from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.outcomes.path import OutcomePathStatus
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    run_feature_strategy_research,
)


def _bars(instrument: str, *, rising: bool, count: int = 90) -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(count):
        close = 100.0 + index * (0.5 if rising else -0.25)
        rows.append(
            DailyBar(
                instrument_id=InstrumentId(instrument),
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
                dataset_version=DatasetVersion("strategy-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_strategy_research_selects_point_in_time_cross_section_and_measures_paths() -> None:
    rising = _bars("rising", rising=True)
    falling = _bars("falling", rising=False)
    strategy = StrategyDefinition(
        strategy_id="positive-20-v0.1",
        name="Positive 20-session return",
        expression="return_20 > 0",
        rank_feature="return_20",
        per_session_limit=1,
    )

    report = run_feature_strategy_research(
        (*rising, *falling),
        strategy=strategy,
        horizons=(5,),
        signal_start=rising[25].trade_date,
        signal_end=rising[40].trade_date,
    )

    assert report.dataset_version == "strategy-test-v1"
    assert report.instrument_count == 2
    assert report.signal_count == 16
    assert {str(item.instrument_id) for item in report.signals} == {"rising"}
    assert all(item.rank_value > 0 for item in report.signals)
    assert report.summaries[0].sample_size == 16
    assert report.summaries[0].mean_return is not None
    assert report.summaries[0].mean_return > 0
    assert all(item.status is OutcomePathStatus.COMPLETE for item in report.outcomes)


def test_future_changes_do_not_change_earlier_strategy_signals() -> None:
    rising = list(_bars("rising", rising=True))
    strategy = StrategyDefinition(
        strategy_id="positive-20-v0.1",
        name="Positive 20-session return",
        expression="return_20 > 0",
        rank_feature="return_20",
        per_session_limit=1,
    )
    cutoff = rising[40].trade_date
    baseline = run_feature_strategy_research(
        tuple(rising),
        strategy=strategy,
        horizons=(5,),
        signal_end=cutoff,
    )
    rising[70] = replace(
        rising[70],
        open_split_adjusted=900.0,
        high_split_adjusted=910.0,
        low_split_adjusted=890.0,
        close_split_adjusted=905.0,
    )
    altered = run_feature_strategy_research(
        tuple(rising),
        strategy=strategy,
        horizons=(5,),
        signal_end=cutoff,
    )

    assert baseline.signals == altered.signals
