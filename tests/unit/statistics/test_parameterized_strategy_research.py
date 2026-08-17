from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.features.parameterized_indicators import (
    IndicatorFamily,
    IndicatorMetric,
    ParameterizedIndicatorSpec,
    compute_parameterized_indicator_frame,
)
from trade_scout.statistics.strategy_research import StrategyDefinition, run_feature_strategy_research


def _bars() -> tuple[DailyBar, ...]:
    rows: list[DailyBar] = []
    for index in range(50):
        close = 100.0 + index
        rows.append(
            DailyBar(
                instrument_id=InstrumentId("tsi_parameterized_strategy"),
                trade_date=date(2024, 1, 2) + timedelta(days=index),
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
                dataset_version=DatasetVersion("parameterized-strategy-v1"),
                quality_status=QualityStatus.PASS,
            )
        )
    return tuple(rows)


def test_parameterized_indicator_uses_existing_signal_and_outcome_path() -> None:
    bars = _bars()
    spec = ParameterizedIndicatorSpec(
        IndicatorFamily.MOVING_AVERAGE,
        IndicatorMetric.MA_DISTANCE_PCT,
        period=7,
    )
    extras = compute_parameterized_indicator_frame(bars, (spec,))
    strategy = StrategyDefinition(
        strategy_id="parameterized-ma-test",
        name="Parameterized MA test",
        expression=f"{spec.feature_name} > 0",
        rank_feature="return_5",
        per_session_limit=10,
    )

    report = run_feature_strategy_research(
        bars,
        strategy=strategy,
        horizons=(2,),
        extra_features=extras,
    )

    assert report.signal_count > 0
    assert report.outcomes
    assert "parameterized-indicators-v0.1" in report.feature_set_version
    assert {signal.event_definition_version for signal in report.signals} == {
        "feature-expression-strategy-signal-v0.1"
    }
