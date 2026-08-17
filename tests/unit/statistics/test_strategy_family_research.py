from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.statistics.strategy_family_research import run_feature_strategy_signal_family
from trade_scout.statistics.strategy_research import (
    StrategyDefinition,
    run_feature_strategy_research,
)


def _bars(instrument: str, *, rising: bool, count: int = 80) -> tuple[DailyBar, ...]:
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
                dataset_version=DatasetVersion("family-test-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_family_runner_matches_independent_signal_selection() -> None:
    bars = (*_bars("up", rising=True), *_bars("down", rising=False))
    strategies = (
        StrategyDefinition(
            strategy_id="positive",
            name="Positive return",
            expression="return_20 > 0",
            rank_feature="return_20",
            per_session_limit=2,
        ),
        StrategyDefinition(
            strategy_id="negative",
            name="Negative return",
            expression="return_20 < 0",
            rank_feature="return_20",
            descending=False,
            per_session_limit=2,
        ),
    )
    start = date(2024, 2, 1)
    end = date(2024, 2, 20)

    family = run_feature_strategy_signal_family(
        bars,
        strategies=strategies,
        signal_start=start,
        signal_end=end,
    )
    independent = tuple(
        run_feature_strategy_research(
            bars,
            strategy=strategy,
            horizons=(5,),
            signal_start=start,
            signal_end=end,
            measure_outcomes=False,
        )
        for strategy in strategies
    )

    assert tuple(report.signals for report in family) == tuple(
        report.signals for report in independent
    )
    assert all(not report.outcomes for report in family)
    assert all(not report.summaries for report in family)
